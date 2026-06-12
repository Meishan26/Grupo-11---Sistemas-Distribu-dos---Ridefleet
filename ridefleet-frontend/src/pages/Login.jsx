import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { api } from "../services/api";

export default function Login() {
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  async function handleLogin(e) {
    e.preventDefault();
    setError("");

    if (!email.trim() || !senha.trim()) {
      setError("Preencha o e-mail e a senha.");
      return;
    }

    setLoading(true);
    try {
      const res = await api.post("/auth/login", { email, senha });
      localStorage.setItem("token", res.data.token);
      localStorage.setItem("user", JSON.stringify({ nome: res.data.nome, id: res.data.id }));
      navigate("/dashboard");
    } catch (err) {
      const msg = err.response?.data?.msg || err.response?.data?.erro || "";
      setError(msg || "E-mail ou senha incorretos.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="page-center">
      <div className="auth-card">
        <div className="auth-logo">🚗 RideFleet</div>
        <p className="auth-subtitle">Bem-vindo de volta! Faça login para continuar.</p>

        {error && (
          <div className="alert alert-error">
            <span>⚠️</span>
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleLogin}>
          <div className="form-group">
            <label className="form-label" htmlFor="email">E-mail</label>
            <input
              id="email"
              className="form-input"
              type="email"
              placeholder="seu@email.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
            />
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="senha">Senha</label>
            <input
              id="senha"
              className="form-input"
              type="password"
              placeholder="••••••••"
              value={senha}
              onChange={(e) => setSenha(e.target.value)}
              autoComplete="current-password"
            />
          </div>

          <button
            type="submit"
            className="btn btn-primary btn-full"
            disabled={loading}
            style={{ marginTop: 8, height: 44 }}
          >
            {loading ? <><span className="spinner" />Entrando…</> : "Entrar"}
          </button>
        </form>

        <p style={{ textAlign: "center", marginTop: 20, fontSize: 14, color: "var(--text-muted)" }}>
          Não tem conta?{" "}
          <Link to="/register">Cadastre-se</Link>
        </p>
      </div>
    </div>
  );
}
