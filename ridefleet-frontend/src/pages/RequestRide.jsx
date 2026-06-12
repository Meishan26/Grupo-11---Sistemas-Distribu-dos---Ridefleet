import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { api } from "../services/api";
import Navbar from "../components/Navbar";

export default function RequestRide() {
  const [origem, setOrigem] = useState("");
  const [destino, setDestino] = useState("");
  const [errors, setErrors] = useState({});
  const [loading, setLoading] = useState(false);
  const [apiError, setApiError] = useState("");
  const navigate = useNavigate();

  function validate() {
    const e = {};
    if (!origem.trim()) e.origem = "Informe o local de origem.";
    if (!destino.trim()) e.destino = "Informe o destino.";
    if (origem.trim() && destino.trim() && origem.trim() === destino.trim())
      e.destino = "Destino deve ser diferente da origem.";
    return e;
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setApiError("");
    const errs = validate();
    if (Object.keys(errs).length) { setErrors(errs); return; }
    setErrors({});
    setLoading(true);

    try {
      const res = await api.post("/rides/solicitar", { origem: origem.trim(), destino: destino.trim() });
      navigate(`/ride/${res.data.corrida_id}`);
    } catch (err) {
      const msg = err.response?.data?.msg || err.response?.data?.erro || "";
      setApiError(msg || "Não foi possível criar a corrida. Tente novamente.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="page-layout">
      <Navbar />
      <div className="container">
        <div style={{ marginBottom: 20 }}>
          <Link to="/dashboard" style={{ fontSize: 13, color: "var(--text-muted)" }}>
            ← Voltar ao início
          </Link>
          <h2 style={{ marginTop: 8, fontSize: 22 }}>Solicitar corrida</h2>
          <p style={{ color: "var(--text-muted)", fontSize: 14, marginTop: 4 }}>
            Informe o ponto de partida e destino para encontrarmos um motorista.
          </p>
        </div>

        <div className="card">
          {apiError && (
            <div className="alert alert-error">
              <span>⚠️</span><span>{apiError}</span>
            </div>
          )}

          <form onSubmit={handleSubmit}>
            {/* Route visual */}
            <div style={{ display: "flex", gap: 16, alignItems: "flex-start" }}>
              {/* Line indicator */}
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", paddingTop: 36 }}>
                <div style={{ width: 12, height: 12, borderRadius: "50%", background: "var(--success)", flexShrink: 0 }} />
                <div style={{ width: 2, height: 32, background: "var(--border)", margin: "4px 0" }} />
                <div style={{ width: 12, height: 12, borderRadius: 2, background: "var(--accent)", flexShrink: 0 }} />
              </div>

              <div style={{ flex: 1 }}>
                <div className="form-group">
                  <label className="form-label" htmlFor="origem">Origem</label>
                  <input
                    id="origem"
                    className={`form-input${errors.origem ? " error" : ""}`}
                    placeholder="Endereço de partida"
                    value={origem}
                    onChange={(e) => { setOrigem(e.target.value); setErrors((p) => ({ ...p, origem: "" })); }}
                  />
                  {errors.origem && <span className="form-error">{errors.origem}</span>}
                </div>

                <div className="form-group">
                  <label className="form-label" htmlFor="destino">Destino</label>
                  <input
                    id="destino"
                    className={`form-input${errors.destino ? " error" : ""}`}
                    placeholder="Para onde você vai?"
                    value={destino}
                    onChange={(e) => { setDestino(e.target.value); setErrors((p) => ({ ...p, destino: "" })); }}
                  />
                  {errors.destino && <span className="form-error">{errors.destino}</span>}
                </div>
              </div>
            </div>

            {/* Map placeholder */}
            <div className="map-placeholder">
              <span className="map-icon">🗺️</span>
              <span>Mapa do percurso</span>
            </div>

            <button
              type="submit"
              className="btn btn-primary btn-full"
              disabled={loading}
              style={{ height: 48, fontSize: 16, marginTop: 4 }}
            >
              {loading ? (
                <><span className="spinner" />Procurando motorista…</>
              ) : (
                "🚕 Solicitar corrida"
              )}
            </button>
          </form>
        </div>

        <div className="alert alert-info" style={{ marginTop: 16 }}>
          <span>ℹ️</span>
          <span>
            Seu pedido será enviado para motoristas próximos. Se não houver disponibilidade local,
            <strong> o sistema pode delegar a corrida via rede RideFleet Core</strong>.
          </span>
        </div>
      </div>
    </div>
  );
}
