import { render, screen } from "@testing-library/react";
import App from "../App";

describe("App", () => {
  it("renders the asset management system heading", () => {
    render(<App />);
    expect(screen.getByText(/Asset Management System/i)).toBeInTheDocument();
  });

  it("renders the scaffold ready h1", () => {
    render(<App />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "Week 1 monorepo scaffold is ready."
    );
  });

  it("renders the description paragraph", () => {
    render(<App />);
    expect(screen.getByText(/FastAPI provides the shared OpenAPI contract/i)).toBeInTheDocument();
  });

  it("renders API docs link", () => {
    render(<App />);
    expect(screen.getByRole("link", { name: /open api docs/i })).toHaveAttribute(
      "href",
      "http://localhost:8000/docs"
    );
  });

  it("renders health check link", () => {
    render(<App />);
    expect(screen.getByRole("link", { name: /health check/i })).toHaveAttribute(
      "href",
      "http://localhost:8000/health"
    );
  });
});
