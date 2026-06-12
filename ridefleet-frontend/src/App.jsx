import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Login from "./pages/Login";
import Register from "./pages/Register";
import Dashboard from "./pages/Dashboard";
import RequestRide from "./pages/RequestRide";
import RideStatus from "./pages/RideStatus";
import RideHistory from "./pages/RideHistory";
import Admin from "./pages/Admin";
import PrivateRoute from "./routes/PrivateRoute";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Navigate to="/login" />} />
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />

        <Route path="/dashboard" element={<PrivateRoute><Dashboard /></PrivateRoute>} />
        <Route path="/request" element={<PrivateRoute><RequestRide /></PrivateRoute>} />
        <Route path="/ride/:id" element={<PrivateRoute><RideStatus /></PrivateRoute>} />
        <Route path="/history" element={<PrivateRoute><RideHistory /></PrivateRoute>} />
        <Route path="/admin"   element={<PrivateRoute><Admin /></PrivateRoute>} />
      </Routes>
    </BrowserRouter>
  );
}
