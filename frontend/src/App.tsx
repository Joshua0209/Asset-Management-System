function App() {
  return (
    <main className="app-shell">
      <section className="hero-card">
        <p className="eyebrow">Asset Management System</p>
        <h1>Week 1 monorepo scaffold is ready.</h1>
        <p className="description">
          FastAPI provides the shared OpenAPI contract, while React + Vite is prepared for the
          Week 2 feature work.
        </p>
        <div className="links">
          <a href="http://localhost:8000/docs" target="_blank" rel="noreferrer">
            Open API Docs
          </a>
          <a href="http://localhost:8000/health" target="_blank" rel="noreferrer">
            Health Check
          </a>
        </div>
      </section>
    </main>
  );
}

export default App;
