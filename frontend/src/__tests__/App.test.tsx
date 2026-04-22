import { render, screen } from "@testing-library/react";
import App from "../App";

describe("App", () => {
  it("renders the manager dashboard heading", () => {
    render(<App />);
    expect(screen.getByRole("heading", { name: /Manager Dashboard/i })).toBeInTheDocument();
  });

  it("renders the sidebar menu items", () => {
    render(<App />);
    // Use getByRole to target the menu items specifically
    expect(screen.getByRole("menuitem", { name: /dashboard/i })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /asset list/i })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /reviews/i })).toBeInTheDocument();
  });

  it("renders the language switcher", () => {
    render(<App />);
    expect(screen.getByText("中")).toBeInTheDocument();
    expect(screen.getByText("EN")).toBeInTheDocument();
  });
});
