import { useEffect, useState, useRef } from "react";
import { useParams, Link } from "react-router-dom";
import { api } from "../services/api";
import Navbar from "../components/Navbar";

const STEPS = [
  { key: "request", label: "Aguardando", icon: "⏳" },
  { key: "match", label: "Motorista encontrado", icon: "👋" },
  { key: "confirm", label: "Confirmado", icon: "✔️" },
  { key: "in_transit", label: "Em trânsito", icon: "🚗" },
  { key: "complete", label: "Concluída", icon: "🏁" },
];

const STEP_INDEX = Object.fromEntries(STEPS.map((s, i) => [s.key, i]));

const STATUS_DESCRIPTION = {
  request: "Procurando motoristas disponíveis na sua área…",
  match: "Um motorista foi encontrado e está a caminho.",
  confirm: "Motorista confirmado. Prepare-se para a viagem.",
  in_transit: "Você está a caminho do seu destino.",
  complete: "Corrida finalizada com sucesso!",
};

const PROGRESS = { request: 10, match: 35, confirm: 60, in_transit: 85, complete: 100 };
const PROGRESS_COLOR = {
  request: "var(--warning)",
  match: "var(--info)",
  confirm: "var(--purple)",
  in_transit: "var(--warning)",
  complete: "var(--success)",
};

export default function RideStatus() {
  const { id } = useParams();
  const [ride, setRide] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const intervalRef = useRef(null);

  async function loadRide() {
    try {
      const res = await api.get(`/rides/status/${id}`);
      setRide(res.data);
      // Stop polling when ride is complete
      if (res.data.status === "complete" && intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    } catch (err) {
      setError(
        err.response?.data?.msg ||
        err.response?.data?.erro ||
        "Não foi possível carregar o status da corrida."
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadRide();
    intervalRef.current = setInterval(loadRide, 3000);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [id]);

  if (loading) {
    return (
      <div className="page-layout">
        <Navbar />
        <div className="loading-center">
          <div className="spinner spinner-lg" style={{ color: "var(--accent)" }} />
          <span>Carregando corrida…</span>
        </div>
      </div>
    );
  }

  if (error || !ride) {
    return (
      <div className="page-layout">
        <Navbar />
        <div className="container">
          <div className="alert alert-error" style={{ marginTop: 24 }}>
            <span>⚠️</span>
            <span>{error || "Corrida não encontrada."}</span>
          </div>
          <Link to="/dashboard" className="btn btn-ghost" style={{ marginTop: 12 }}>
            ← Voltar ao início
          </Link>
        </div>
      </div>
    );
  }

  const stepIdx = STEP_INDEX[ride.status] ?? 0;
  const progress = PROGRESS[ride.status] ?? 0;
  const progressColor = PROGRESS_COLOR[ride.status] ?? "var(--accent)";
  const isComplete = ride.status === "complete";
  const isWaiting = ride.status === "request";

  return (
    <div className="page-layout">
      <Navbar />
      <div className="container">
        <div style={{ marginBottom: 16 }}>
          <Link to="/dashboard" style={{ fontSize: 13, color: "var(--text-muted)" }}>
            ← Voltar ao início
          </Link>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 8 }}>
            <h2 style={{ fontSize: 20 }}>Corrida #{id.toString().slice(0, 8)}</h2>
            {!isComplete && (
              <span style={{ fontSize: 12, color: "var(--text-muted)", display: "flex", alignItems: "center", gap: 6 }}>
                <span className="spinner" style={{ width: 12, height: 12, color: "var(--accent)" }} />
                Atualizando…
              </span>
            )}
          </div>
        </div>

        {/* Status card */}
        <div className="card" style={{ marginBottom: 16 }}>
          {/* Progress bar */}
          <div className="progress-wrap" style={{ marginBottom: 20 }}>
            <div
              className="progress-bar"
              style={{ width: `${progress}%`, background: progressColor }}
            />
          </div>

          {/* Status label */}
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 8 }}>
            <span style={{ fontSize: 28 }}>{STEPS[stepIdx]?.icon}</span>
            <div>
              <div style={{ fontWeight: 700, fontSize: 18, color: "var(--text-h)" }}>
                {STEPS[stepIdx]?.label}
              </div>
              <div style={{ fontSize: 14, color: "var(--text-muted)", marginTop: 2 }} className={isWaiting ? "pulse" : ""}>
                {STATUS_DESCRIPTION[ride.status]}
              </div>
            </div>
          </div>

          {/* Steps */}
          <div className="steps">
            {STEPS.map((step, i) => (
              <div
                key={step.key}
                className={`step ${i < stepIdx ? "done" : i === stepIdx ? "active" : ""}`}
              >
                <div className="step-dot">
                  {i < stepIdx ? "✓" : step.icon}
                </div>
                <div className="step-label">{step.label}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Delegation banner */}
        {ride.delegada && (
          <div className="delegation-banner">
            <div className="delegation-icon">🔗</div>
            <div>
              <div className="delegation-title">Corrida delegada via RideFleet Core</div>
              <p style={{ fontSize: 13, color: "var(--text)", margin: "4px 0 0" }}>
                Não havia motoristas disponíveis localmente. O sistema encontrou um motorista
                através da rede compartilhada.
              </p>
              {ride.servico_origem && (
                <div className="delegation-detail">
                  <span>🏢</span>
                  <span>Serviço de origem: <strong>{ride.servico_origem}</strong></span>
                </div>
              )}
              {ride.core_ride_uuid && (
                <div className="delegation-detail">
                  <span>🆔</span>
                  <span>Core ID: <strong style={{ fontFamily: "monospace", fontSize: 12 }}>{ride.core_ride_uuid}</strong></span>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Driver card */}
        {ride.motorista && (
          <div className="driver-card">
            <div className="driver-avatar">🧑‍✈️</div>
            <div>
              <div className="driver-name">{ride.motorista.nome ?? ride.motorista}</div>
              <div className="driver-meta">
                {ride.motorista.veiculo && `${ride.motorista.veiculo} · `}
                {ride.motorista.placa && `${ride.motorista.placa} · `}
                {ride.status === "match" && "A caminho do local de partida"}
                {ride.status === "confirm" && "Aguardando no local"}
                {ride.status === "in_transit" && "Em viagem com você"}
                {ride.status === "complete" && "Viagem concluída"}
              </div>
            </div>
            {ride.eta_minutos != null && (
              <div className="eta-chip">
                <div className="eta-label">ETA</div>
                <div className="eta-value">{ride.eta_minutos}min</div>
              </div>
            )}
          </div>
        )}

        {/* Map placeholder */}
        <div className="map-placeholder">
          <span className="map-icon">🗺️</span>
          <span>Mapa de acompanhamento do motorista</span>
          {ride.motorista && (
            <span style={{ fontSize: 12 }}>Motorista: {ride.motorista.nome ?? ""}</span>
          )}
        </div>

        {/* Route info */}
        <div className="card">
          <div className="info-row">
            <span className="info-icon">🟢</span>
            <span className="info-key">Origem</span>
            <span className="info-val">{ride.origem}</span>
          </div>
          <div className="info-row">
            <span className="info-icon">📍</span>
            <span className="info-key">Destino</span>
            <span className="info-val">{ride.destino}</span>
          </div>
          {ride.status && (
            <div className="info-row">
              <span className="info-icon">🔄</span>
              <span className="info-key">Status</span>
              <span className="info-val">{STEPS[stepIdx]?.label}</span>
            </div>
          )}
          {ride.id && (
            <div className="info-row">
              <span className="info-icon">🆔</span>
              <span className="info-key">ID</span>
              <span className="info-val" style={{ fontFamily: "monospace", fontSize: 13 }}>
                {ride.id}
              </span>
            </div>
          )}
        </div>

        {/* Completed state */}
        {isComplete && (
          <div className="alert alert-success" style={{ marginTop: 16 }}>
            <span>🎉</span>
            <span>Corrida concluída! Esperamos que tenha sido uma ótima viagem.</span>
          </div>
        )}

        {isComplete && (
          <div style={{ display: "flex", gap: 10, marginTop: 12 }}>
            <Link to="/request" className="btn btn-primary" style={{ flex: 1, justifyContent: "center" }}>
              Nova corrida
            </Link>
            <Link to="/dashboard" className="btn btn-ghost" style={{ flex: 1, justifyContent: "center" }}>
              Ver histórico
            </Link>
          </div>
        )}
      </div>
    </div>
  );
}
