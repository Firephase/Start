"""
CLI for EMRI Step 1 geodesic simulations.

Usage:
    emri run --config configs/circular.yaml
    emri run --mode circular --r0 10.0 --tau-max 500
    emri info --r0 10.0
    emri potential --L 3.46 --E 0.97
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import typer
import yaml
import numpy as np
from rich.console import Console
from rich.table import Table

app = typer.Typer(name="emri", help="EMRI Step 1 — Schwarzschild geodesic simulator")
console = Console()


def _load_config(path: Path):
    from emri_step1.models.parameters import SimulationConfig
    with open(path) as f:
        data = yaml.safe_load(f)
    return SimulationConfig(**data)


def _run_simulation(cfg):
    from emri_step1.physics.hamiltonian import SchwarzschildHamiltonian
    from emri_step1.physics.geodesic import GeodesicSolver
    from emri_step1.models.parameters import OrbitMode

    ham = SchwarzschildHamiltonian()
    solver = GeodesicSolver(ham)

    orbit = cfg.orbit
    mode = orbit.mode

    if mode == OrbitMode.circular:
        E, L, y0 = solver.ic_from_circular(orbit.r0, orbit.phi0)
    elif mode == OrbitMode.turning_points:
        E, L, y0 = solver.ic_from_turning_points(orbit.r_peri, orbit.r_apo, orbit.phi0)
    elif mode == OrbitMode.pe_params:
        from emri_step1.physics.circular import CircularOrbitAnalyzer
        r_peri, r_apo = CircularOrbitAnalyzer.pe_to_turning_points(orbit.p_param, orbit.e_param)
        E, L, y0 = solver.ic_from_turning_points(r_peri, r_apo, orbit.phi0)
    elif mode == OrbitMode.el_direct:
        y0 = solver.initial_conditions(orbit.r_start, orbit.phi0, orbit.E, orbit.L, orbit.pr0)
        E, L = orbit.E, orbit.L
    else:
        console.print(f"[red]Unknown orbit mode: {mode}[/red]")
        raise typer.Exit(1)

    console.print(f"[cyan]Integrating: E={E:.6f}, L={L:.6f}[/cyan]")
    result = solver.run(E, L, y0, cfg.solver)
    return result, E, L


@app.command("run")
def run_cmd(
    config: Optional[Path] = typer.Option(None, "--config", "-c", help="YAML config file"),
    mode: str = typer.Option("circular", "--mode", help="Orbit mode: circular / turning_points / el_direct / pe_params"),
    r0: Optional[float] = typer.Option(None, "--r0", help="Circular orbit radius"),
    E: Optional[float] = typer.Option(None, "--E", help="Energy"),
    L: Optional[float] = typer.Option(None, "--L", help="Angular momentum"),
    r_peri: Optional[float] = typer.Option(None, "--r-peri", help="Periastron radius"),
    r_apo: Optional[float] = typer.Option(None, "--r-apo", help="Apastron radius"),
    tau_max: float = typer.Option(2000.0, "--tau-max", help="Integration proper time"),
    rtol: float = typer.Option(1e-10, "--rtol"),
    atol: float = typer.Option(1e-12, "--atol"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output CSV path"),
    plot: bool = typer.Option(False, "--plot", help="Show matplotlib orbit plot"),
):
    """Run a geodesic simulation."""
    from emri_step1.models.parameters import (
        SimulationConfig, OrbitConfig, SolverConfig, OrbitMode
    )

    if config:
        cfg = _load_config(config)
    else:
        orbit_mode = OrbitMode(mode)
        orbit_kwargs: dict = {"mode": orbit_mode}
        if orbit_mode == OrbitMode.circular:
            if r0 is None:
                console.print("[red]--r0 required for circular mode[/red]"); raise typer.Exit(1)
            orbit_kwargs["r0"] = r0
        elif orbit_mode == OrbitMode.turning_points:
            if r_peri is None or r_apo is None:
                console.print("[red]--r-peri and --r-apo required[/red]"); raise typer.Exit(1)
            orbit_kwargs["r_peri"] = r_peri
            orbit_kwargs["r_apo"] = r_apo
        elif orbit_mode == OrbitMode.el_direct:
            if E is None or L is None or r0 is None:
                console.print("[red]--E, --L, --r0 required for el_direct mode[/red]"); raise typer.Exit(1)
            orbit_kwargs.update({"E": E, "L": L, "r_start": r0})

        cfg = SimulationConfig(
            orbit=OrbitConfig(**orbit_kwargs),
            solver=SolverConfig(tau_max=tau_max, rtol=rtol, atol=atol),
        )

    result, e_val, l_val = _run_simulation(cfg)

    # Summary table
    table = Table(title="Simulation Results")
    table.add_column("Quantity", style="cyan")
    table.add_column("Value", style="green")

    T_r = result.estimated_radial_period
    table.add_row("E", f"{e_val:.8f}")
    table.add_row("L", f"{l_val:.8f}")
    table.add_row("r_min", f"{result.r_min:.6f}")
    table.add_row("r_max", f"{result.r_max:.6f}")
    table.add_row("H max drift", f"{result.H_max_drift:.2e}")
    table.add_row("N steps", str(result.n_steps))
    table.add_row("Wall time", f"{result.wall_time:.3f} s")
    table.add_row("Solver", result.solver_message)
    if T_r:
        table.add_row("Est. radial period τ_r", f"{T_r:.4f}")
    table.add_row("Plunge?", "YES ⚠" if result.is_plunge else "No")

    console.print(table)

    if output:
        df = result.to_dataframe()
        df.to_csv(output, index=False)
        console.print(f"[green]Saved trajectory to {output}[/green]")

    if plot:
        import matplotlib.pyplot as plt
        fig, axes = plt.subplots(1, 2, figsize=(12, 5))
        axes[0].plot(result.x, result.y_cart, lw=0.8)
        circ = plt.Circle((0, 0), 2.0, color="black", fill=True, alpha=0.3, label="Horizon")
        axes[0].add_patch(circ)
        axes[0].set_aspect("equal")
        axes[0].set_xlabel("x/M"); axes[0].set_ylabel("y/M")
        axes[0].set_title("Orbit (Cartesian)")
        axes[0].legend()

        axes[1].plot(result.tau, result.H_residual, color="crimson", lw=0.8)
        axes[1].axhline(0, color="black", lw=0.5)
        axes[1].set_xlabel("τ/M"); axes[1].set_ylabel("ΔH")
        axes[1].set_title("Hamiltonian drift")

        plt.tight_layout()
        plt.show()


@app.command("info")
def info_cmd(
    r0: float = typer.Option(10.0, "--r0", help="Radius for circular orbit analysis"),
):
    """Print circular orbit parameters for a given radius."""
    from emri_step1.physics.circular import CircularOrbitAnalyzer

    analyzer = CircularOrbitAnalyzer()
    try:
        info = analyzer.analyze(r0)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    table = Table(title=f"Circular Orbit at r₀ = {r0}")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("E", f"{info.E:.8f}")
    table.add_row("L", f"{info.L:.8f}")
    table.add_row("Stable?", "Yes" if info.is_stable else "No (unstable)")
    table.add_row("ISCO?", "Yes" if info.is_isco else "No")
    table.add_row("Ω = dφ/dt", f"{info.omega:.8f}")
    table.add_row("T_φ (coord)", f"{info.T_phi:.4f} M")
    table.add_row("T_φ (proper)", f"{info.T_tau:.4f} M")
    console.print(table)


@app.command("potential")
def potential_cmd(
    L: float = typer.Option(3.46, "--L", help="Angular momentum"),
    E: Optional[float] = typer.Option(None, "--E", help="Energy (marks level on plot)"),
    r_min: float = typer.Option(2.1, "--r-min"),
    r_max: float = typer.Option(30.0, "--r-max"),
):
    """Plot V_eff(r; L) with optional energy level."""
    import matplotlib.pyplot as plt
    from emri_step1.physics.potential import EffectivePotential

    veff = EffectivePotential(L)
    r_arr, v_arr = veff.plot_data((r_min, r_max))

    plt.figure(figsize=(8, 4))
    plt.plot(r_arr, v_arr, label=f"V_eff (L={L})")
    if E is not None:
        plt.axhline(E**2, color="red", linestyle="--", label=f"E² = {E**2:.4f}")
    plt.axvline(2.0, color="black", label="Horizon")
    plt.axvline(6.0, color="orange", linestyle="--", label="ISCO r=6")
    plt.xlabel("r / M"); plt.ylabel("V_eff")
    plt.title(f"Schwarzschild Effective Potential (L={L})")
    plt.legend(); plt.tight_layout(); plt.show()


if __name__ == "__main__":
    app()
