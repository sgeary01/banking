import React, { useEffect, useState } from 'react';
import { getCustomerAccounts, getAccountTransactions, deposit, withdraw, transfer } from '../services/api';

const s = {
  card: { background: '#fff', borderRadius: 10, padding: 20, boxShadow: '0 2px 8px rgba(0,0,0,0.06)', marginBottom: 16 },
  h2: { fontSize: 16, fontWeight: 600, marginBottom: 12, color: '#333' },
  accountCard: { border: '1px solid #e8e8e8', borderRadius: 8, padding: 16, marginBottom: 12, cursor: 'pointer' },
  selectedCard: { border: '2px solid #6c63ff', borderRadius: 8, padding: 16, marginBottom: 12, cursor: 'pointer' },
  badge: color => ({ background: color, color: '#fff', padding: '2px 10px', borderRadius: 10, fontSize: 11, fontWeight: 600, display: 'inline-block' }),
  input: { padding: '8px 12px', border: '1px solid #ddd', borderRadius: 6, width: '100%', fontSize: 14, marginBottom: 8 },
  btn: color => ({ background: color, color: '#fff', border: 'none', padding: '8px 16px', borderRadius: 6, cursor: 'pointer', fontSize: 13, fontWeight: 600, marginRight: 8 }),
  row: { display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid #f5f5f5', fontSize: 14 },
  error: { color: '#d00', fontSize: 13, marginTop: 8 },
  success: { color: '#52c41a', fontSize: 13, marginTop: 8 },
};

const typeColor = t => ({ checking: '#6c63ff', savings: '#52c41a', credit: '#fa8c16' }[t] || '#888');
const txColor = t => ({ deposit: '#52c41a', withdrawal: '#ff4d4f', transfer: '#6c63ff' }[t] || '#888');

export default function Accounts({ customerId }) {
  const [accounts, setAccounts] = useState([]);
  const [selected, setSelected] = useState(null);
  const [transactions, setTransactions] = useState([]);
  const [form, setForm] = useState({ amount: '', description: '', destAccount: '' });
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

      if (action === 'deposit') await deposit({ account_id: selected.id, amount, description: form.description || 'Deposit' });
      if (action === 'withdraw') await withdraw({ account_id: selected.id, amount, description: form.description || 'Withdrawal' });
      if (action === 'transfer') {
        if (!form.destAccount) throw new Error('Enter destination account ID');
        await transfer({ source_account_id: selected.id, destination_account_id: form.destAccount, amount, description: form.description || 'Transfer' });
      }

      setMsg({ text: `${action} successful!`, ok: true });
      setForm({ amount: '', description: '', destAccount: '' });
      // Refresh
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

  if (!customerId) return <div style={s.card}>No customer linked.</div>;

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '280px 1fr', gap: 16 }}>
      {/* Account list */}
      <div>
        <div style={s.card}>
          <div style={s.h2}>Your Accounts</div>
          {accounts.map(a => (
            <div key={a.id} style={selected?.id === a.id ? s.selectedCard : s.accountCard} onClick={() => selectAccount(a)}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                <span style={s.badge(typeColor(a.account_type))}>{a.account_type}</span>
                <span style={{ fontSize: 11, color: '#aaa' }}>{a.account_number}</span>
              </div>
              <div style={{ fontSize: 20, fontWeight: 700 }}>${a.balance.toFixed(2)}</div>
              <div style={{ fontSize: 11, color: a.status === 'active' ? '#52c41a' : '#ff4d4f', marginTop: 4 }}>{a.status}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Actions + transactions */}
      {selected && (
        <div>
          <div style={s.card}>
            <div style={s.h2}>Transact — {selected.account_number}</div>
            <input style={s.input} type="number" placeholder="Amount" value={form.amount} onChange={e => setForm({ ...form, amount: e.target.value })} />
            <input style={s.input} placeholder="Description (optional)" value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} />
            <input style={s.input} placeholder="Destination account ID (transfer only)" value={form.destAccount} onChange={e => setForm({ ...form, destAccount: e.target.value })} />
            <div>
              <button style={s.btn('#52c41a')} onClick={() => doAction('deposit')} disabled={loading}>Deposit</button>
              <button style={s.btn('#ff4d4f')} onClick={() => doAction('withdraw')} disabled={loading}>Withdraw</button>
              <button style={s.btn('#6c63ff')} onClick={() => doAction('transfer')} disabled={loading}>Transfer</button>
            </div>
            {msg.text && <div style={msg.ok ? s.success : s.error}>{msg.text}</div>}
          </div>

          <div style={s.card}>
            <div style={s.h2}>Recent Transactions</div>
            {transactions.map(tx => (
              <div key={tx.id} style={s.row}>
                <div>
                  <span style={{ ...s.badge(txColor(tx.transaction_type)), marginRight: 8 }}>{tx.transaction_type}</span>
                  {tx.description}
                </div>
                <div style={{ fontWeight: 600 }}>
                  {tx.destination_account_id === selected.id ? '+' : '-'}${tx.amount.toFixed(2)}
                  <span style={{ color: '#aaa', fontSize: 11, marginLeft: 8 }}>{new Date(tx.created_at).toLocaleDateString()}</span>
                </div>
              </div>
            ))}
            {transactions.length === 0 && <p style={{ color: '#aaa', fontSize: 13 }}>No transactions</p>}
          </div>
        </div>
      )}
    </div>
  );
}
