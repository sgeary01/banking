import React, { useEffect, useState } from 'react';
import { getChaosScenarios, triggerScenario, clearAllChaos, injectChaos, generateLoad, getCustomerAccounts } from '../services/api';

const s = {
  card: { background: '#fff', borderRadius: 10, padding: 20, boxShadow: '0 2px 8px rgba(0,0,0,0.06)', marginBottom: 16 },
  h2: { fontSize: 16, fontWeight: 600, marginBottom: 12, color: '#333' },
  scenarioCard: { border: '1px solid #e8e8e8', borderRadius: 8, padding: 16, marginBottom: 10, display: 'flex', justifyContent: 'space-between', alignItems: 'center' },
  btn: (color, outline) => ({
    background: outline ? '#fff' : color, color: outline ? color : '#fff',
    border: `1px solid ${color}`, padding: '8px 18px', borderRadius: 6,
    cursor: 'pointer', fontSize: 13, fontWeight: 600, marginRight: 8,
  }),
  input: { padding: '7px 12px', border: '1px solid #ddd', borderRadius: 6, fontSize: 13, width: '100%', marginBottom: 8 },
  select: { padding: '7px 12px', border: '1px solid #ddd', borderRadius: 6, fontSize: 13, marginBottom: 8, width: '100%' },
  msg: ok => ({ padding: '10px 14px', borderRadius: 6, fontSize: 13, marginTop: 10, background: ok ? '#f6ffed' : '#fff0f0', color: ok ? '#52c41a' : '#d00' }),
  warning: { background: '#fff7e6', border: '1px solid #ffd591', borderRadius: 8, padding: 12, marginBottom: 16, fontSize: 13, color: '#874d00' },
};

const SERVICES = ['transaction-service', 'account-service', 'fraud-service', 'notification-service'];

export default function ChaosPanel({ customerId }) {
  const [scenarios, setScenarios] = useState([]);
  const [accountIds, setAccountIds] = useState([]);
  const [msg, setMsg] = useState(null);
  const [manual, setManual] = useState({ service: SERVICES[0], latency_ms: 0, error_rate: 0 });
  const [load, setLoad] = useState({ count: 20, high_value: false });

  useEffect(() => {
    getChaosScenarios().then(r => setScenarios(r.data));
    if (customerId) {
      getCustomerAccounts(customerId).then(r => setAccountIds(r.data.map(a => a.id)));
    }
  }, [customerId]);

  const notify = (text, ok = true) => { setMsg({ text, ok }); setTimeout(() => setMsg(null), 4000); };

  const trigger = async name => {
    try {
      await triggerScenario(name, accountIds);
      notify(`Scenario "${name}" triggered — watch your metrics!`);
    } catch (e) { notify(e.response?.data?.detail || 'Failed', false); }
  };

  const clearAll = async () => {
    try { await clearAllChaos(); notify('All chaos cleared'); } catch (e) { notify('Failed to clear', false); }
  };

  const inject = async () => {
    try {
      await injectChaos({ service: manual.service, latency_ms: parseInt(manual.latency_ms), error_rate: parseFloat(manual.error_rate) });
      notify(`Chaos injected into ${manual.service}`);
    } catch (e) { notify('Failed to inject', false); }
  };

  const genLoad = async () => {
    if (!accountIds.length) { notify('No accounts found', false); return; }
    try {
      await generateLoad(accountIds, load.count, load.high_value);
      notify(`Generating ${load.count} transactions${load.high_value ? ' (high value!)' : ''}…`);
    } catch (e) { notify('Failed to generate load', false); }
  };

  return (
    <div>
      <div style={s.warning}>
        ⚡ <strong>Chaos Panel</strong> — these actions intentionally degrade services to generate O11y signals.
        Open Grafana / Resolve before triggering. Use <em>Clear All Chaos</em> to restore normal operation.
      </div>

      {msg && <div style={s.msg(msg.ok)}>{msg.text}</div>}

      {/* Scenarios */}
      <div style={s.card}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <div style={s.h2}>Scenarios</div>
          <button style={s.btn('#52c41a')} onClick={clearAll}>Clear All Chaos</button>
        </div>
        {scenarios.map(sc => (
          <div key={sc.name} style={s.scenarioCard}>
            <div>
              <div style={{ fontWeight: 600, marginBottom: 4 }}>{sc.name.replace(/_/g, ' ').toUpperCase()}</div>
              <div style={{ fontSize: 13, color: '#666' }}>{sc.description}</div>
            </div>
            <button style={s.btn('#ff4d4f')} onClick={() => trigger(sc.name)}>Trigger</button>
          </div>
        ))}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        {/* Manual injection */}
        <div style={s.card}>
          <div style={s.h2}>Manual Injection</div>
          <label style={{ fontSize: 12, color: '#888' }}>Service</label>
          <select style={s.select} value={manual.service} onChange={e => setManual({ ...manual, service: e.target.value })}>
            {SERVICES.map(svc => <option key={svc}>{svc}</option>)}
          </select>
          <label style={{ fontSize: 12, color: '#888' }}>Latency (ms)</label>
          <input style={s.input} type="number" min="0" value={manual.latency_ms} onChange={e => setManual({ ...manual, latency_ms: e.target.value })} />
          <label style={{ fontSize: 12, color: '#888' }}>Error Rate (0.0 – 1.0)</label>
          <input style={s.input} type="number" min="0" max="1" step="0.1" value={manual.error_rate} onChange={e => setManual({ ...manual, error_rate: e.target.value })} />
          <button style={s.btn('#fa8c16')} onClick={inject}>Inject</button>
        </div>

        {/* Load generator */}
        <div style={s.card}>
          <div style={s.h2}>Transaction Load Generator</div>
          <p style={{ fontSize: 13, color: '#888', marginBottom: 12 }}>
            Fire transactions against your seeded accounts. High-value mode triggers fraud alerts.
          </p>
          <label style={{ fontSize: 12, color: '#888' }}>Transaction Count</label>
          <input style={s.input} type="number" min="1" max="200" value={load.count} onChange={e => setLoad({ ...load, count: e.target.value })} />
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, marginBottom: 12 }}>
            <input type="checkbox" checked={load.high_value} onChange={e => setLoad({ ...load, high_value: e.target.checked })} />
            High-value amounts ($5k–$15k) — triggers fraud detection
          </label>
          <button style={s.btn('#6c63ff')} onClick={genLoad}>Generate Load</button>
          <div style={{ fontSize: 12, color: '#aaa', marginTop: 8 }}>Using {accountIds.length} account(s)</div>
        </div>
      </div>
    </div>
  );
}
