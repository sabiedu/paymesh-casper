import { Routes, Route } from "react-router-dom";
import Shell from "./components/Shell";
import DashboardPage from "./pages/DashboardPage";
import ObservePage from "./pages/ObservePage";
import DemoPage from "./pages/DemoPage";

export default function App() {
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route index element={<DashboardPage />} />
        <Route path="observe" element={<ObservePage />} />
        <Route path="demo" element={<DemoPage />} />
        <Route path="*" element={<DashboardPage />} />
      </Route>
    </Routes>
  );
}
