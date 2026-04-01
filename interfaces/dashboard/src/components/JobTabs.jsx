export const PROFILES = [
  { id: "yassir", label: "Yassir", scope: "individual" },
  { id: "zeal", label: "Zeal", scope: "leader" },
  { id: "freelance", label: "Freelance", scope: "individual" },
  { id: "", label: "All Jobs", scope: "all" },
];

export default function JobTabs({ active, onChange }) {
  return (
    <nav className="job-tabs">
      {PROFILES.map((p) => (
        <button
          key={p.id}
          className={`job-tab ${active === p.id ? "active" : ""}`}
          onClick={() => onChange(p.id)}
        >
          {p.label}
          <span className="tab-scope">{p.scope}</span>
        </button>
      ))}
    </nav>
  );
}
