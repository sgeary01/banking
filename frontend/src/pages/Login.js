import React, { useState } from 'react';
import { login } from '../services/api';

const s = {
  page: { minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#f5f7fa' },
  card: { background: '#fff', borderRadius: 12, padding: 40, width: 380, boxShadow: '0 4px 24px rgba(0,0,0,0.08)' },
  logo: { textAlign: 'center', fontSize: 22, fontWeight: 700, color: '#6c63ff', marginBottom: 8 },
  sub: { textAlign: 'center', color: '#888', fontSize: 14, marginBottom: 28 },
  label: { display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 6, color: '#333' },
  input: { width: '100%', padding: '10px 14px', borderRadius: 8, border: '1px solid #ddd', fontSize: 14, marginBottom: 16, outline: 'none' },
  btn: { width: '100%', padding: '12px', background: '#6c63ff', color: '#fff', border: 'none', borderRadius: 8, fontSize: 15, fontWeight: 600, cursor: 'pointer' },
  error: { background: '#fff0f0', color: '#d00', padding: '10px 14px', borderRadius: 8, fontSize: 13, marginBottom: 16 },
  hint: { textAlign: 'center', color: '#aaa', fontSize: 12, marginTop: 20 },
};

export default function Login({ onLogin }) {
  const [email, setEmail] = useState('alice@example.com');
  const [password, setPassword] = useState('password123');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async e => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      const res = await login(email, password);
      onLogin(res.data.access_token, res.data.customer_id);
    } catch (err) {
      setError(err.response?.data?.detail || 'Login failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={s.page}>
      <div style={s.card}>
        <div style={s.logo}>RESOLVE BANK</div>
        <div style={s.sub}>O11y Demo Platform</div>
        {error && <div style={s.error}>{error}</div>}
        <form onSubmit={handleSubmit}>
          <label style={s.label}>Email</label>
          <input style={s.input} type="email" value={email} onChange={e => setEmail(e.target.value)} required />
          <label style={s.label}>Password</label>
          <input style={s.input} type="password" value={password} onChange={e => setPassword(e.target.value)} required />
          <button style={s.btn} type="submit" disabled={loading}>
            {loading ? 'Signing in…' : 'Sign In'}
          </button>
        </form>
        <div style={s.hint}>Seed users: alice@example.com / password123</div>
      </div>
    </div>
  );
}
