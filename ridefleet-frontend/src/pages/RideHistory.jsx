import { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { api } from "../services/api";
import Navbar from "../components/Navbar";

const STATUS_LABEL = {
  request: "Aguardando",
  match: "Motorista encontrado",
  confirm: "Confirmado",
  in_transit: "Em trânsito",
  complete: "Concluída",
};

const STATUS_CLASS = {
  request: "badge-waiting",
  match: "badge-info",
  confirm: "badge-purple",
  in_transit: "badge-moving",
  complete: "badge-success",
};

const STATUS_ICON = {
  request: "⏳",
  match: "🔵",
  confirm: "🟣",
  in_transit: "🚗",
  complete: "✅",
};

function formatDate(iso) {
  if (!iso) return "";
  try {
    return new Intl.DateTimeFormat("pt-BR", {
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}

export default function RideHistory() {
  const [rides, setRides] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("all");
  const navigate = useNavigate();

  useEffect(() => {
    api
      .get("/rides/minhas")
      .then((res) => setRides(res.data?.corridas || res.data || []))
      .catch(() => setError("Não foi possível carregar o histórico."))
      .finally(() => setLoading(false));
  }, []);

  const filtered =
    filter === "all"
      ? rides
      : filter === "active"
      ? rides.filter((r) => r.status !== "complete")
      : rides.filter((r) => r.status === "complete");

  return (
    <div className="page-layout">
      <Navbar />
      <div className="container">
        <div style={{ marginBottom: 20 }}>
          <Link to="/dashboard" style={{ fontSize: 13, color: "var(--text-muted)" }}>
            ← Voltar ao início
          </Link>
          <h2 style={{ marginTop: 8, fontSize: 22 }}>Histórico de corridas</h2>
          <p style={{ color: "var(--text-muted)", fontSize: 14, marginTop: 4 }}>
            {rides.length} corrida{rides.length !== 1 ? "s" : ""} no total
          </p>
        </div>

        {/* Filter tabs */}
        <div style={{ display: "flex", gap: 8, marginBottom: 20 }}>
          {[
            { key: "all", label: "Todas" },
            { key: "active", label: "Em andamento" },
            { key: "done", label: "Concluídas" },
          ].map((f) => (
            <button
              key={f.key}
              className={`btn btn-sm ${filter === f.key ? "btn-primary" : "btn-ghost"}`}
              onClick={() => setFilter(f.key)}
            >
              {f.label}
            </button>
          ))}
        </div>

        {error && (
          <div className="alert alert-error">
            <span>⚠️</span><span>{error}</span>
          </div>
        )}

        {loading ? (
          <div className="loading-center">
            <div className="spinner spinner-lg" style={{ color: "var(--accent)" }} />
            <span>Carregando histórico…</span>
          </div>
        ) : filtered.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">🚗</div>
            <h3>Nenhuma corrida encontrada</h3>
            <p>
              {filter !== "all"
                ? "Tente outro filtro."
                : "Solicite sua primeira corrida!"}
            </p>
            {filter === "all" && (
              <Link to="/request" className="btn btn-primary" style={{ marginTop: 16 }}>
                Solicitar corrida
              </Link>
            )}
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {filtered.map((ride) => {
              const label = STATUS_LABEL[ride.status] || ride.status;
              const cls = STATUS_CLASS[ride.status] || "badge-info";
              const icon = STATUS_ICON[ride.status] || "🚗";
              return (
                <div
                  key={ride.id}
                  className="ride-item"
                  onClick={() => navigate(`/ride/${ride.id}`)}
                >
                  <div className="ride-item-icon" style={{ background: "var(--accent-light)" }}>
                    {icon}
                  </div>
                  <div className="ride-item-body">
                    <div className="ride-item-route">
                      {ride.origem} → {ride.destino}
                    </div>
                    <div className="ride-item-meta">
                      {ride.motorista && `Motorista: ${ride.motorista.nome ?? ride.motorista} · `}
                      {formatDate(ride.criado_em || ride.created_at)}
                      {ride.delegada && " · 🔗 Delegada"}
                    </div>
                  </div>
                  <div className="ride-item-status">
                    <span className={`badge ${cls}`}>{label}</span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
