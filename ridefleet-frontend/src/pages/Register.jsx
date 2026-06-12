import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { api } from "../services/api";

export default function Register() {
  const [nome, setNome] = useState("");
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [errors, setErrors] = useState({});
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const navigate = useNavigate();

  function validate() {
    const e = {};
    if (!nome.trim()) e.nome = "Nome é obrigatório.";
    if (!email.trim() || !/\S+@\S+\.\S+/.test(email)) e.email = "E-mail inválido.";
    if (senha.length < 6) e.senha = "Senha deve ter ao menos 6 caracteres.";
    return e;
  }

  async function handleSubmit(e) {
    e.preventDefault();
    const errs = validate();
    if (Object.keys(errs).length) { setErrors(errs); return; }
    setErrors({});
    setLoading(true);
    try {
      await api.post("/auth/cadastro", { nome, email, senha });
      setSuccess(true);
      setTimeout(() => navigate("/login"), 1500);
    } catch (err) {
      const msg = err.response?.data?.msg || err.response?.data?.erro || "";
      setErrors({ global: msg || "Erro ao criar conta. Tente novamente." });
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="page-center">
      <div className="auth-card">
        <div className="auth-logo">🚗 RideFleet</div>
        <p className="auth-subtitle">Crie sua conta para solicitar corridas.</p>

        {errors.global && (
          <div className="alert alert-error">
            <span>⚠️</span><span>{errors.global}</span>
          </div>
        )}
        {success && (
          <div className="alert alert-success">
            <span>✅</span><span>Conta criada! Redirecionando…</span>
          </div>
        )}

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label className="form-label" htmlFor="nome">Nome completo</label>
            <input
              id="nome"
              className={`form-input${errors.nome ? " error" : ""}`}
              placeholder="João Silva"
              value={nome}
              onChange={(e) => setNome(e.target.value)}
            />
            {errors.nome && <span className="form-error">{errors.nome}</span>}
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="email">E-mail</label>
            <input
              id="email"
              className={`form-input${errors.email ? " error" : ""}`}
              type="email"
              placeholder="seu@email.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
            {errors.email && <span className="form-error">{errors.email}</span>}
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="senha">Senha</label>
            <input
              id="senha"
              className={`form-input${errors.senha ? " error" : ""}`}
              type="password"
              placeholder="Mínimo 6 caracteres"
              value={senha}
              onChange={(e) => setSenha(e.target.value)}
            />
            {errors.senha && <span className="form-error">{errors.senha}</span>}
          </div>

          <button
            type="submit"
            className="btn btn-primary btn-full"
            disabled={loading}
            style={{ marginTop: 8, height: 44 }}
          >
            {loading ? <><span className="spinner" />Criando conta…</> : "Criar conta"}
          </button>
        </form>

        <p style={{ textAlign: "center", marginTop: 20, fontSize: 14, color: "var(--text-muted)" }}>
          Já tem conta?{" "}
          <Link to="/login">Entrar</Link>
        </p>
      </div>
    </div>
  );
}
