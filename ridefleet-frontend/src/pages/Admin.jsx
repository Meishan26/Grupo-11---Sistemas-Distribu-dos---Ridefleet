import { useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import { api } from "../services/api";
import Navbar from "../components/Navbar";

const STATUS_MOTORISTA = {
  disponivel: { label: "Disponível", color: "var(--success)", bg: "var(--success-light)" },
  ocupado:    { label: "Ocupado",    color: "var(--warning)", bg: "var(--warning-light)" },
  offline:    { label: "Offline",    color: "var(--text-muted)", bg: "var(--border)" },
};

const STATUS_CORRIDA = {
  request:    { label: "Aguardando",         color: "var(--warning)" },
  match:      { label: "Motorista alocado",  color: "var(--info)" },
  confirm:    { label: "Confirmado",          color: "var(--purple)" },
  in_transit: { label: "Em trânsito",         color: "#d97706" },
  complete:   { label: "Concluída",           color: "var(--success)" },
  cancelled:  { label: "Cancelada",           color: "var(--danger)" },
};

const TIPO_CORRIDA = {
  local:           { label: "Local",              icon: "🏠", color: "var(--info)",    bg: "var(--info-light)" },
  recebida_do_core:{ label: "Recebida do Core",   icon: "📥", color: "var(--purple)",  bg: "var(--purple-light)" },
  enviada_ao_core: { label: "Enviada ao Core",    icon: "📤", color: "var(--warning)", bg: "var(--warning-light)" },
};

function formatTime(iso) {
  if (!iso) return "—";
  try {
    return new Intl.DateTimeFormat("pt-BR", {
      hour: "2-digit", minute: "2-digit", second: "2-digit",
    }).format(new Date(iso));
  } catch { return iso; }
}

export default function Admin() {
  const [data, setData]       = useState(null);
  const [lastUpdate, setLastUpdate] = useState(null);
  const [error, setError]     = useState("");
  const [tick, setTick]       = useState(0);

  const carregar = useCallback(() => {
    api.get("/admin/painel")
      .then((res) => {
        setData(res.data);
        setLastUpdate(new Date());
        setError("");
      })
      .catch(() => setError("Não foi possível carregar o painel."));
  }, []);

  useEffect(() => { carregar(); }, [carregar]);

  // Atualiza a cada 5 segundos
  useEffect(() => {
    const id = setInterval(() => {
      setTick((t) => t + 1);
      carregar();
    }, 5000);
    return () => clearInterval(id);
  }, [carregar]);

  const stats = data?.stats;
  const motoristas = data?.motoristas || [];
  const corridas   = data?.corridas   || [];

  return (
    <div className="page-layout">
      <Navbar />
      <div className="container-wide">

        {/* Cabeçalho */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 24, marginTop: 8 }}>
          <div>
            <Link to="/dashboard" style={{ fontSize: 13, color: "var(--text-muted)" }}>← Voltar</Link>
            <h2 style={{ marginTop: 6, fontSize: 22 }}>⚙️ Painel Administrativo</h2>
            <p style={{ color: "var(--text-muted)", fontSize: 13, marginTop: 4 }}>
              Monitoramento em tempo real · grupo-11
            </p>
          </div>
          <div style={{ textAlign: "right" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span style={{
                width: 8, height: 8, borderRadius: "50%",
                background: error ? "var(--danger)" : "var(--success)",
                display: "inline-block",
                animation: error ? "none" : "pulse 2s infinite",
              }} />
              <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
                {error ? "Sem conexão" : "Ao vivo"}
              </span>
            </div>
            {lastUpdate && (
              <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>
                Atualizado às {formatTime(lastUpdate.toISOString())}
              </div>
            )}
          </div>
        </div>

        {error && (
          <div className="alert alert-error" style={{ marginBottom: 20 }}>
            <span>⚠️</span><span>{error}</span>
          </div>
        )}

        {/* Stats de motoristas */}
        {stats && (
          <>
            <p style={{ fontSize: 13, fontWeight: 600, color: "var(--text-muted)", marginBottom: 10, textTransform: "uppercase", letterSpacing: "0.05em" }}>
              Motoristas
            </p>
            <div className="stats-grid" style={{ marginBottom: 28 }}>
              <StatCard value={stats.motoristas.total}      label="Total"       color="var(--accent)" />
              <StatCard value={stats.motoristas.disponivel} label="Disponíveis" color="var(--success)" />
              <StatCard value={stats.motoristas.ocupado}    label="Ocupados"    color="var(--warning)" />
              <StatCard value={stats.motoristas.offline}    label="Offline"     color="var(--text-muted)" />
            </div>

            <p style={{ fontSize: 13, fontWeight: 600, color: "var(--text-muted)", marginBottom: 10, textTransform: "uppercase", letterSpacing: "0.05em" }}>
              Corridas
            </p>
            <div className="stats-grid" style={{ marginBottom: 32 }}>
              <StatCard value={stats.corridas.total}            label="Total"              color="var(--accent)" />
              <StatCard value={stats.corridas.locais}           label="Locais"             color="var(--info)" />
              <StatCard value={stats.corridas.recebidas_do_core}label="Recebidas do Core"  color="var(--purple)" />
              <StatCard value={stats.corridas.enviadas_ao_core} label="Enviadas ao Core"   color="var(--warning)" />
              <StatCard value={stats.corridas.em_andamento}     label="Em andamento"       color="var(--success)" />
            </div>
          </>
        )}

        {/* Tabela de motoristas */}
        <div style={{ marginBottom: 32 }}>
          <div className="section-header">
            <h3 className="section-title">🧑‍✈️ Motoristas ({motoristas.length})</h3>
          </div>
          {motoristas.length === 0 ? (
            <div className="empty-state"><div className="empty-icon">🧑‍✈️</div><p>Nenhum motorista.</p></div>
          ) : (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: 12 }}>
              {motoristas.map((m) => {
                const s = STATUS_MOTORISTA[m.status] || STATUS_MOTORISTA.offline;
                return (
                  <div key={m.id} className="card" style={{ padding: 16, display: "flex", alignItems: "center", gap: 14 }}>
                    <div style={{
                      width: 44, height: 44, borderRadius: "50%",
                      background: s.bg, display: "flex", alignItems: "center",
                      justifyContent: "center", fontSize: 20, flexShrink: 0,
                    }}>🧑‍✈️</div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontWeight: 600, fontSize: 14, color: "var(--text-h)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                        {m.nome}
                      </div>
                      <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
                        {m.veiculo} · {m.placa}
                      </div>
                    </div>
                    <span style={{
                      padding: "4px 10px", borderRadius: 100, fontSize: 12, fontWeight: 500,
                      background: s.bg, color: s.color, flexShrink: 0,
                    }}>{s.label}</span>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Tabela de corridas */}
        <div style={{ marginBottom: 32 }}>
          <div className="section-header">
            <h3 className="section-title">🚗 Corridas recentes ({corridas.length})</h3>
          </div>
          {corridas.length === 0 ? (
            <div className="empty-state"><div className="empty-icon">🚗</div><p>Nenhuma corrida registrada.</p></div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {corridas.map((c) => {
                const tipo   = TIPO_CORRIDA[c.tipo]   || TIPO_CORRIDA.local;
                const status = STATUS_CORRIDA[c.status] || { label: c.status, color: "var(--text-muted)" };
                return (
                  <div key={c.id} className="card" style={{ padding: "14px 18px", display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap" }}>

                    {/* Tipo badge */}
                    <span style={{
                      padding: "4px 10px", borderRadius: 100, fontSize: 12, fontWeight: 500,
                      background: tipo.bg, color: tipo.color, flexShrink: 0, whiteSpace: "nowrap",
                    }}>
                      {tipo.icon} {tipo.label}
                    </span>

                    {/* Rota */}
                    <div style={{ flex: 1, minWidth: 160 }}>
                      <div style={{ fontWeight: 600, fontSize: 13, color: "var(--text-h)" }}>
                        {c.origem} → {c.destino}
                      </div>
                      <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>
                        {c.tipo === "recebida_do_core" && `📥 Origem: ${c.servico_origem}`}
                        {c.tipo === "enviada_ao_core"  && `📤 Leilão Core`}
                        {c.tipo === "local"            && `🏠 Atendida localmente`}
                        {c.core_ride_uuid && ` · UUID: ${c.core_ride_uuid.slice(0, 8)}…`}
                      </div>
                    </div>

                    {/* Motorista */}
                    <div style={{ fontSize: 12, color: "var(--text-muted)", minWidth: 120 }}>
                      {c.motorista
                        ? `🧑‍✈️ ${c.motorista.nome}`
                        : <span style={{ fontStyle: "italic" }}>Sem motorista</span>}
                    </div>

                    {/* Horário */}
                    <div style={{ fontSize: 11, color: "var(--text-muted)", minWidth: 60, textAlign: "right" }}>
                      {formatTime(c.criado_em)}
                    </div>

                    {/* Status */}
                    <span style={{
                      padding: "4px 10px", borderRadius: 100, fontSize: 12, fontWeight: 500,
                      background: "transparent", border: `1px solid ${status.color}`,
                      color: status.color, flexShrink: 0, whiteSpace: "nowrap",
                    }}>
                      {status.label}
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </div>

      </div>
    </div>
  );
}

function StatCard({ value, label, color }) {
  return (
    <div className="stat-card">
      <div className="stat-value" style={{ color }}>{value ?? "—"}</div>
      <div className="stat-label">{label}</div>
    </div>
  );
}
