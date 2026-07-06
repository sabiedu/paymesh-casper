import DemoConsole from "../components/DemoConsole";
import { useShell } from "../components/Shell";

export default function DemoPage() {
  const { services, refresh } = useShell();
  return (
    <div className="demo-page">
      <DemoConsole services={services} onAfterAction={refresh} />
    </div>
  );
}
