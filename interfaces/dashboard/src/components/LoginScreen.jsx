import { useState } from "react";
import { verifyPin } from "../api";
import { Lock } from "lucide-react";

export default function LoginScreen({ onLogin }) {
  const [pin, setPin] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      await verifyPin(pin);
      onLogin(pin);
    } catch {
      setError("Invalid PIN");
      setPin("");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-screen">
      <div className="login-card">
        <div className="login-icon"><Lock size={32} /></div>
        <h1>Nerve Center</h1>
        <p className="login-subtitle">Multi-Agent Operations Platform</p>
        <form onSubmit={handleSubmit}>
          <input
            type="password"
            placeholder="Enter PIN"
            value={pin}
            onChange={(e) => setPin(e.target.value)}
            autoFocus
            maxLength={10}
          />
          <button type="submit" disabled={loading || !pin}>
            {loading ? "Verifying..." : "Unlock"}
          </button>
          {error && <p className="login-error">{error}</p>}
        </form>
      </div>
    </div>
  );
}
