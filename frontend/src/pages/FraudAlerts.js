import React, { useEffect, useState } from 'react';
import { getFraudAlerts } from '../services/api';
import api from '../services/api';

const s = {
  card: { background: '#fff', borderRadius: 10, padding: 20, boxShadow: '0 2px 8px rgba(0,0,0,0.06)' },
  h2: { fontSize: 16, fontWeight: 600, marginBottom: 16, color: '#333' },
  table: { width: '100%', borderCollapse: 'collapse', fontSize: 13 },
  th: { textAlign: 'left', padding: '10px 12px', borderBottom: '2px solid #f0f0f0', color: '#888', fontWeight: 600, fontSize: 12 },
  td: { padding: '10px 12px', borderBottom: '1px solid #f5f5f5', verticalAlign: 'top' },
  badge: color => ({ background: color, color: '#fff', padding: '2px 8px', borderRadius: 10, fontSize: 11, fontWeight: 600 }),
  risk: score => ({ color: score > 0.7 ? '#f5222d' : score > 0.4 ? '#fa8c16' : '#52c41a', fontWeight: 700 }),
  btn: { padding: '4px 10px', border: '1px solid #ddd', borderRadius: 4, cursor: 'pointer', fontSize: 12, background: '#fff' },
};

const statusColor = s => ({ open: '#ff4d4f', reviewed: '#fa8c16', dismissed: '#8c8c8c' }[s] || '#888');

export default function FraudAlerts() {
  const [alerts, setAlerts] = useState([]);
  const [filter, setFilter] = useState('open');
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    const r = await getFraudAlerts(filter === 'all' ? undefined : filter, 100);
    setAlerts(r.data);
    setLoading(false);
  };

  useEffect(() => { load(); }, [filter]);

  const updateStatus = async (alertId, status) => {
    await api.patch(`/fraud/alerts/${alertId}/status`, null, { params: { status } });
    load();
  };

  return (
    <div style={s.card}>
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 16 }}>
        <div style={s.h2}>Fraud Alerts</div>
        <div style={{ marginLeft: 'auto' }}>
          {['open', 'reviewed', 'dismissed', 'all'].map(f => (
            <button key={f} onClick={() => setFilter(f)}
              style={{ padding: '6px 14px', border: '1px solid #ddd', borderRadius: 6, marginRight: 6, cursor: 'pointer', fontSize: 13,
                background: filter === f ? '#6c63ff' : '#fff', color: filter === f ? '#fff' : '#333' }}>
              {f}
            </button>
          ))}
          <button onClick={load} style={{ padding: '6px 14px', border: '1px solid #ddd', borderRadius: 6, cursor: 'pointer', fontSize: 13 }}>Refresh</button>
        </div>
      </div>

      {loading ? <p style={{ color: '#aaa' }}>Loading…</p> : (
        <table style={s.table}>
          <thead>
            <tr>
              <th style={s.th}>Risk Score</th>
              <th style={s.th}>Account</th>
              <th style={s.th}>Reasons</th>
              <th style={s.th}>Status</th>
              <th style={s.th}>Time</th>
              <th style={s.th}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {alerts.map(a => (
              <tr key={a.id}>
                <td style={s.td}><span style={s.risk(a.risk_score)}>{(a.risk_score * 100).toFixed(0)}%</span></td>
                <td style={{ ...s.td, fontFamily: 'monospace', fontSize: 11 }}>{a.account_id.slice(0, 8)}…</td>
                <td style={s.td}>
                  {a.reasons.map((r, i) => <div key={i} style={{ marginBottom: 2, color: '#555' }}>• {r}</div>)}
                </td>
                <td style={s.td}><span style={s.badge(statusColor(a.status))}>{a.status}</span></td>
                <td style={{ ...s.td, color: '#888', fontSize: 11 }}>{new Date(a.created_at).toLocaleString()}</td>
                <td style={s.td}>
                  {a.status === 'open' && (
                    <>
                      <button style={s.btn} onClick={() => updateStatus(a.id, 'reviewed')}>Review</button>
                      <button style={{ ...s.btn, marginLeft: 4 }} onClick={() => updateStatus(a.id, 'dismissed')}>Dismiss</button>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {!loading && alerts.length === 0 && <p style={{ color: '#aaa', fontSize: 13 }}>No alerts</p>}
    </div>
  );
}
