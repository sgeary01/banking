import React, { useEffect, useState } from 'react';
import { getCustomerAccounts, getAccountTransactions } from '../services/api';

const s = {
  card: { background: '#fff', borderRadius: 10, padding: 20, boxShadow: '0 2px 8px rgba(0,0,0,0.06)' },
  h2: { fontSize: 16, fontWeight: 600, marginBottom: 16, color: '#333' },
  table: { width: '100%', borderCollapse: 'collapse', fontSize: 13 },
  th: { textAlign: 'left', padding: '10px 12px', borderBottom: '2px solid #f0f0f0', color: '#888', fontWeight: 600, fontSize: 12 },
  td: { padding: '10px 12px', borderBottom: '1px solid #f5f5f5' },
  badge: color => ({ background: color, color: '#fff', padding: '2px 8px', borderRadius: 10, fontSize: 11, fontWeight: 600 }),
  filter: { padding: '7px 12px', border: '1px solid #ddd', borderRadius: 6, fontSize: 13, marginRight: 8 },
};

const typeColor = t => ({ deposit: '#52c41a', withdrawal: '#ff4d4f', transfer: '#6c63ff' }[t] || '#888');
const statusColor = s => ({ completed: '#52c41a', pending: '#fa8c16', failed: '#ff4d4f', flagged: '#f5222d' }[s] || '#888');

export default function Transactions({ customerId }) {
  const [transactions, setTransactions] = useState([]);
  const [filter, setFilter] = useState('all');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!customerId) return;
    setLoading(true);
    getCustomerAccounts(customerId).then(async r => {
      const all = [];
      for (const acct of r.data) {
        const txRes = await getAccountTransactions(acct.id, 50);
        all.push(...txRes.data);
      }
      all.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
      // Deduplicate by id
      const seen = new Set();
      setTransactions(all.filter(t => { if (seen.has(t.id)) return false; seen.add(t.id); return true; }));
      setLoading(false);
    });
  }, [customerId]);

  const visible = filter === 'all' ? transactions : transactions.filter(t => t.transaction_type === filter);

  return (
    <div style={s.card}>
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 16 }}>
        <div style={s.h2}>All Transactions</div>
        <div style={{ marginLeft: 'auto' }}>
          {['all', 'deposit', 'withdrawal', 'transfer'].map(f => (
            <button key={f} onClick={() => setFilter(f)}
              style={{ ...s.filter, background: filter === f ? '#6c63ff' : '#fff', color: filter === f ? '#fff' : '#333', cursor: 'pointer' }}>
              {f}
            </button>
          ))}
        </div>
      </div>

      {loading ? <p style={{ color: '#aaa' }}>Loading…</p> : (
        <table style={s.table}>
          <thead>
            <tr>
              <th style={s.th}>Type</th>
              <th style={s.th}>Description</th>
              <th style={s.th}>Amount</th>
              <th style={s.th}>Status</th>
              <th style={s.th}>Date</th>
            </tr>
          </thead>
          <tbody>
            {visible.map(tx => (
              <tr key={tx.id}>
                <td style={s.td}><span style={s.badge(typeColor(tx.transaction_type))}>{tx.transaction_type}</span></td>
                <td style={s.td}>{tx.description || '—'}</td>
                <td style={{ ...s.td, fontWeight: 600 }}>${tx.amount.toFixed(2)}</td>
                <td style={s.td}><span style={s.badge(statusColor(tx.status))}>{tx.status}</span></td>
                <td style={{ ...s.td, color: '#888' }}>{new Date(tx.created_at).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {!loading && visible.length === 0 && <p style={{ color: '#aaa', fontSize: 13 }}>No transactions found</p>}
    </div>
  );
}
