import { Link, useNavigate } from "react-router-dom";

export default function Navbar() {
  const navigate = useNavigate();
  const user = (() => {
    try { return JSON.parse(localStorage.getItem("user") || "{}"); }
    catch { return {}; }
  })();

  function handleLogout() {
    localStorage.removeItem("token");
    localStorage.removeItem("user");
    navigate("/login");
  }

  return (
    <nav className="navbar">
      <Link to="/dashboard" className="navbar-brand" style={{ textDecoration: "none" }}>
        🚗 RideFleet
      </Link>
      <div className="navbar-actions">
        {user.nome && <span className="navbar-user">Olá, {user.nome.split(" ")[0]}</span>}
        <Link to="/admin" className="btn btn-ghost btn-sm">
          ⚙️ Admin
        </Link>
        <Link to="/request" className="btn btn-primary btn-sm">
          + Nova corrida
        </Link>
        <button className="btn btn-ghost btn-sm" onClick={handleLogout}>
          Sair
        </button>
      </div>
    </nav>
  );
}
