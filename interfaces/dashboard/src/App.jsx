import { useState } from "react";
import LoginScreen from "./components/LoginScreen";
import JobTabs from "./components/JobTabs";
import BriefingPanel from "./components/BriefingPanel";
import TicketList from "./components/TicketList";
import PRDigest from "./components/PRDigest";
import TicketSummary from "./components/TicketSummary";
import BlockerAlerts from "./components/BlockerAlerts";
import ActivityFeed from "./components/ActivityFeed";
import AgentHealth from "./components/AgentHealth";
import QueryBar from "./components/QueryBar";
import "./App.css";

export default function App() {
  const [authenticated, setAuthenticated] = useState(
    () => sessionStorage.getItem("nc_auth") === "1"
  );
  const [activeProfile, setActiveProfile] = useState("yassir");

  const handleLogin = () => {
    sessionStorage.setItem("nc_auth", "1");
    setAuthenticated(true);
  };

  if (!authenticated) {
    return <LoginScreen onLogin={handleLogin} />;
  }

  return (
    <div className="app">
      <header className="app-header">
        <div className="header-left">
          <h1 className="app-title">Nerve Center</h1>
        </div>
        <JobTabs active={activeProfile} onChange={setActiveProfile} />
        <div className="header-right">
          <button
            className="btn-sm"
            onClick={() => {
              sessionStorage.removeItem("nc_auth");
              setAuthenticated(false);
            }}
          >
            Lock
          </button>
        </div>
      </header>

      <main className="app-main">
        <QueryBar profileId={activeProfile} />

        <div className="dashboard-grid">
          <div className="grid-col-main">
            <BriefingPanel profileId={activeProfile} />
            <ActivityFeed profileId={activeProfile} />
            <TicketList profileId={activeProfile} />
          </div>
          <div className="grid-col-side">
            <BlockerAlerts profileId={activeProfile} />
            <TicketSummary profileId={activeProfile} />
            <PRDigest profileId={activeProfile} />
            <AgentHealth />
          </div>
        </div>
      </main>
    </div>
  );
}
