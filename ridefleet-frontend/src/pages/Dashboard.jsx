import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
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
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}

export default function Dashboard() {
  const [rides, setRides] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const navigate = useNavigate();

  useEffect(() => {
    api
      .get("/rides/minhas")
      .then((res) => setRides(res.data?.corridas || res.data || []))
      .catch(() => setError("Não foi possível carregar o histórico."))
      .finally(() => setLoading(false));
  }, []);

  const active = rides.filter((r) => r.status !== "complete");
  const completed = rides.filter((r) => r.status === "complete");

  return (
    <div className="page-layout">
      <Navbar />
      <div className="container-wide">
        {/* Hero CTA */}
        <div
          className="card card-lg"
          style={{
            marginBottom: 24,
            marginTop: 8,
            background: "linear-gradient(135deg, var(--accent-light), var(--info-light))",
            borderColor: "var(--accent)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 20,
            flexWrap: "wrap",
          }}
        >
          <div>
            <h2 style={{ fontSize: 22, marginBottom: 6 }}>Para onde vamos hoje?</h2>
            <p style={{ color: "var(--text-muted)", fontSize: 14 }}>
              Solicite uma corrida e acompanhe em tempo real.
            </p>
          </div>
          <Link to="/request" className="btn btn-primary" style={{ fontSize: 15, padding: "12px 28px" }}>
            🚕 Solicitar corrida
          </Link>
        </div>

        {/* Stats */}
        <div className="stats-grid">
          <div className="stat-card">
            <div className="stat-value">{rides.length}</div>
            <div className="stat-label">Total de corridas</div>
          </div>
          <div className="stat-card">
            <div className="stat-value" style={{ color: "var(--success)" }}>
              {completed.length}
            </div>
            <div className="stat-label">Concluídas</div>
          </div>
          <div className="stat-card">
            <div className="stat-value" style={{ color: "var(--warning)" }}>
              {active.length}
            </div>
            <div className="stat-label">Em andamento</div>
          </div>
        </div>

        {/* Active rides */}
        {active.length > 0 && (
          <div style={{ marginBottom: 28 }}>
            <div className="section-header">
              <h3 className="section-title">🔄 Em andamento</h3>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {active.map((ride) => (
                <RideItem key={ride.id} ride={ride} onClick={() => navigate(`/ride/${ride.id}`)} />
              ))}
            </div>
          </div>
        )}

        {/* History */}
        <div>
          <div className="section-header">
            <h3 className="section-title">📋 Histórico</h3>
            {rides.length > 0 && (
              <Link to="/history" style={{ fontSize: 13 }}>
                Ver todas
              </Link>
            )}
          </div>

          {error && (
            <div className="alert alert-error">
              <span>⚠️</span><span>{error}</span>
            </div>
          )}

          {loading ? (
            <div className="loading-center">
              <div className="spinner spinner-lg" style={{ color: "var(--accent)" }} />
              <span>Carregando corridas…</span>
            </div>
          ) : completed.length === 0 && active.length === 0 ? (
            <div className="empty-state">
              <div className="empty-icon">🚗</div>
              <h3>Nenhuma corrida ainda</h3>
              <p>Solicite sua primeira corrida e ela aparecerá aqui.</p>
              <Link to="/request" className="btn btn-primary" style={{ marginTop: 16 }}>
                Solicitar corrida
              </Link>
            </div>
          ) : completed.length === 0 ? null : (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {completed.slice(0, 5).map((ride) => (
                <RideItem key={ride.id} ride={ride} onClick={() => navigate(`/ride/${ride.id}`)} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function RideItem({ ride, onClick }) {
  const label = STATUS_LABEL[ride.status] || ride.status;
  const cls = STATUS_CLASS[ride.status] || "badge-info";
  const icon = STATUS_ICON[ride.status] || "🚗";

  return (
    <div className="ride-item" onClick={onClick} style={{ cursor: "pointer" }}>
      <div
        className="ride-item-icon"
        style={{ background: "var(--accent-light)" }}
      >
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
}
