import React, { useEffect, useState } from 'react';
import { getCustomerOverview, getFraudAlerts } from '../services/api';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';

const s = {
  grid: { display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16, marginBottom: 24 },
  card: { background: '#fff', borderRadius: 10, padding: 20, boxShadow: '0 2px 8px rgba(0,0,0,0.06)' },
  statVal: { fontSize: 28, fontWeight: 700, color: '#1E40AF', marginTop: 8 },
  statLabel: { fontSize: 13, color: '#888' },
  h2: { fontSize: 16, fontWeight: 600, marginBottom: 16, color: '#333' },
  row: { display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid #f0f0f0', fontSize: 14 },
  badge: (color) => ({ background: color, color: '#fff', padding: '2px 8px', borderRadius: 10, fontSize: 11, fontWeight: 600 }),
  alertBadge: { background: '#ff4d4f', color: '#fff', padding: '2px 8px', borderRadius: 10, fontSize: 11, fontWeight: 600 },
};

// Backend stores deposit/withdrawal/transfer; UI shows insurance-flavored labels.
const TX_LABEL = { deposit: 'Premium', withdrawal: 'Claim Payout', transfer: 'Internal' };
const txColor = type => ({ deposit: '#52c41a', withdrawal: '#1E40AF', transfer: '#8c8c8c' }[type] || '#888');

export default function Dashboard({ customerId }) {
  const [overview, setOverview] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [error, setError] = useState('');

  useEffect(() => {
    if (customerId) {
      getCustomerOverview(customerId).then(r => setOverview(r.data)).catch(() => setError('Could not load overview'));
      getFraudAlerts('open', 5).then(r => setAlerts(r.data)).catch(() => {});
    }
  }, [customerId]);

  if (!customerId) return <div style={s.card}><p>No member ID linked to this login. Check seed data.</p></div>;
  if (error) return <div style={{ ...s.card, color: '#d00' }}>{error}</div>;
  if (!overview) return <div style={s.card}><p>Loading…</p></div>;

  const { customer, accounts, total_balance, recent_transactions } = overview;

  const txChartData = ['deposit', 'withdrawal', 'transfer'].map(type => ({
    type: TX_LABEL[type],
    count: recent_transactions.filter(t => t.transaction_type === type).length,
  }));

  return (
    <div>
      <h1 style={{ marginBottom: 20, fontSize: 20, fontWeight: 700 }}>
        Welcome back, {customer.first_name} {customer.last_name}
      </h1>

      {/* Stats row */}
      <div style={s.grid}>
        <div style={s.card}>
          <div style={s.statLabel}>Total Coverage Value</div>
          <div style={s.statVal}>${total_balance.toLocaleString('en-US', { minimumFractionDigits: 2 })}</div>
        </div>
        <div style={s.card}>
          <div style={s.statLabel}>Active Policies</div>
          <div style={s.statVal}>{accounts.length}</div>
        </div>
        <div style={s.card}>
          <div style={s.statLabel}>Open Claim Investigations</div>
          <div style={{ ...s.statVal, color: alerts.length > 0 ? '#ff4d4f' : '#52c41a' }}>{alerts.length}</div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1.5fr 1fr', gap: 16 }}>
        {/* Recent claims */}
        <div style={s.card}>
          <div style={s.h2}>Recent Claims & Payments</div>
          {recent_transactions.slice(0, 8).map(tx => (
            <div key={tx.id} style={s.row}>
              <div>
                <span style={{ ...s.badge(txColor(tx.transaction_type)), marginRight: 8 }}>{TX_LABEL[tx.transaction_type] || tx.transaction_type}</span>
                {tx.description || '—'}
              </div>
              <div style={{ fontWeight: 600, color: tx.transaction_type === 'deposit' ? '#52c41a' : '#333' }}>
                {tx.transaction_type === 'deposit' ? '+' : '-'}${tx.amount.toFixed(2)}
              </div>
            </div>
          ))}
          {recent_transactions.length === 0 && <p style={{ color: '#aaa', fontSize: 13 }}>No activity yet</p>}
        </div>

        {/* Activity chart */}
        <div style={s.card}>
          <div style={s.h2}>Claims Activity Mix</div>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={txChartData}>
              <XAxis dataKey="type" tick={{ fontSize: 12 }} />
              <YAxis tick={{ fontSize: 12 }} />
              <Tooltip />
              <Bar dataKey="count" fill="#1E40AF" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>

          {alerts.length > 0 && (
            <div style={{ marginTop: 16 }}>
              <div style={s.h2}>Open Investigations</div>
              {alerts.map(a => (
                <div key={a.id} style={s.row}>
                  <span>Risk: {(a.risk_score * 100).toFixed(0)}%</span>
                  <span style={s.alertBadge}>OPEN</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
