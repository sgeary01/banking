import React, { useEffect, useState } from 'react';
import { getCustomerAccounts, getAccountTransactions, deposit, withdraw } from '../services/api';

const s = {
  card: { background: '#fff', borderRadius: 10, padding: 20, boxShadow: '0 2px 8px rgba(0,0,0,0.06)', marginBottom: 16 },
  h2: { fontSize: 16, fontWeight: 600, marginBottom: 12, color: '#333' },
  accountCard: { border: '1px solid #e8e8e8', borderRadius: 8, padding: 16, marginBottom: 12, cursor: 'pointer' },
  selectedCard: { border: '2px solid #1E40AF', borderRadius: 8, padding: 16, marginBottom: 12, cursor: 'pointer' },
  badge: color => ({ background: color, color: '#fff', padding: '2px 10px', borderRadius: 10, fontSize: 11, fontWeight: 600, display: 'inline-block' }),
  input: { padding: '8px 12px', border: '1px solid #ddd', borderRadius: 6, width: '100%', fontSize: 14, marginBottom: 8 },
  btn: color => ({ background: color, color: '#fff', border: 'none', padding: '8px 16px', borderRadius: 6, cursor: 'pointer', fontSize: 13, fontWeight: 600, marginRight: 8 }),
  row: { display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid #f5f5f5', fontSize: 14 },
  error: { color: '#d00', fontSize: 13, marginTop: 8 },
  success: { color: '#52c41a', fontSize: 13, marginTop: 8 },
};

// Each insurance policy type renders with its own badge color. Falls back to gray
// for any legacy or unrecognized type (so old banking data still displays).
const typeColor = t => ({
  'Term Life': '#1E40AF',
  'Whole Life': '#0F4C81',
  'Disability': '#7C3AED',
  'Dental': '#10B981',
  'Vision': '#F59E0B',
  'Pet': '#EC4899',
  checking: '#888', savings: '#888', credit: '#888',
}[t] || '#888');

const TX_LABEL = { deposit: 'Premium', withdrawal: 'Claim', transfer: 'Internal' };
const txColor = t => ({ deposit: '#52c41a', withdrawal: '#1E40AF', transfer: '#8c8c8c' }[t] || '#888');

export default function Policies({ customerId }) {
  const [accounts, setAccounts] = useState([]);
  const [selected, setSelected] = useState(null);
  const [transactions, setTransactions] = useState([]);
  const [form, setForm] = useState({ amount: '', description: '' });
  const [msg, setMsg] = useState({ text: '', ok: true });
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (customerId) {
      getCustomerAccounts(customerId).then(r => {
        setAccounts(r.data);
        if (r.data.length) selectAccount(r.data[0]);
      });
    }
  }, [customerId]);

  const selectAccount = async acct => {
    setSelected(acct);
    const r = await getAccountTransactions(acct.id, 20);
    setTransactions(r.data);
  };

  const doAction = async action => {
    setLoading(true);
    setMsg({ text: '', ok: true });
    try {
      const amount = parseFloat(form.amount);
      if (!amount || amount <= 0) throw new Error('Enter a valid amount');

      if (action === 'premium') await deposit({ account_id: selected.id, amount, description: form.description || 'Premium payment' });
      if (action === 'claim') await withdraw({ account_id: selected.id, amount, description: form.description || 'Claim submission' });

      setMsg({ text: action === 'premium' ? 'Premium payment recorded.' : 'Claim submitted for review.', ok: true });
      setForm({ amount: '', description: '' });
      const r = await getCustomerAccounts(customerId);
      setAccounts(r.data);
      const updated = r.data.find(a => a.id === selected.id);
      if (updated) selectAccount(updated);
    } catch (e) {
      setMsg({ text: e.response?.data?.detail || e.message, ok: false });
    } finally {
      setLoading(false);
    }
  };

  if (!customerId) return <div style={s.card}>No member ID linked.</div>;

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '300px 1fr', gap: 16 }}>
      {/* Policy list */}
      <div>
        <div style={s.card}>
          <div style={s.h2}>Your Policies</div>
          {accounts.map(a => (
            <div key={a.id} style={selected?.id === a.id ? s.selectedCard : s.accountCard} onClick={() => selectAccount(a)}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                <span style={s.badge(typeColor(a.account_type))}>{a.account_type}</span>
                <span style={{ fontSize: 11, color: '#aaa' }}>{a.account_number}</span>
              </div>
              <div style={{ fontSize: 11, color: '#888', marginTop: 2 }}>Coverage</div>
              <div style={{ fontSize: 20, fontWeight: 700 }}>${a.balance.toFixed(2)}</div>
              <div style={{ fontSize: 11, color: a.status === 'active' ? '#52c41a' : '#ff4d4f', marginTop: 4 }}>{a.status}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Actions + activity */}
      {selected && (
        <div>
          <div style={s.card}>
            <div style={s.h2}>{selected.account_type} — {selected.account_number}</div>
            <input style={s.input} type="number" placeholder="Amount" value={form.amount} onChange={e => setForm({ ...form, amount: e.target.value })} />
            <input style={s.input} placeholder="Description (e.g. 'Annual physical', 'Dental cleaning')" value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} />
            <div>
              <button style={s.btn('#52c41a')} onClick={() => doAction('premium')} disabled={loading}>Pay Premium</button>
              <button style={s.btn('#1E40AF')} onClick={() => doAction('claim')} disabled={loading}>Submit Claim</button>
            </div>
            {msg.text && <div style={msg.ok ? s.success : s.error}>{msg.text}</div>}
          </div>

          <div style={s.card}>
            <div style={s.h2}>Recent Activity</div>
            {transactions.map(tx => (
              <div key={tx.id} style={s.row}>
                <div>
                  <span style={{ ...s.badge(txColor(tx.transaction_type)), marginRight: 8 }}>{TX_LABEL[tx.transaction_type] || tx.transaction_type}</span>
                  {tx.description}
                </div>
                <div style={{ fontWeight: 600 }}>
                  {tx.destination_account_id === selected.id ? '+' : '-'}${tx.amount.toFixed(2)}
                  <span style={{ color: '#aaa', fontSize: 11, marginLeft: 8 }}>{new Date(tx.created_at).toLocaleDateString()}</span>
                </div>
              </div>
            ))}
            {transactions.length === 0 && <p style={{ color: '#aaa', fontSize: 13 }}>No activity</p>}
          </div>
        </div>
      )}
    </div>
  );
}
