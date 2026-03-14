from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple


@dataclass
class StepProfile:
    """
    Perfil piecewise-constant lido de CSV.
    Colunas obrigatórias: time_s (int), <value_col> (float).
    O valor vigente é o último ponto com time_s <= t_s.
    """
    points: List[Tuple[int, float]]

    def value(self, t_s: int, default: float) -> float:
        if not self.points:
            return default
        v = default
        for t, val in self.points:
            if t_s >= t:
                v = val
            else:
                break
        return v

    @staticmethod
    def from_csv(path: str | Path, time_col: str, value_col: str) -> "StepProfile":
        pts: List[Tuple[int, float]] = []
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                pts.append((int(row[time_col]), float(row[value_col])))
        pts.sort(key=lambda x: x[0])
        return StepProfile(points=pts)


@dataclass
class LoadProfile:
    """
    Perfil de carga piecewise-constant.
    CSV: time_s, P_load_kW, Q_load_kVAr
    """
    points: List[Tuple[int, float, float]]

    def value(
        self, t_s: int, default_p_kw: float, default_q_kvar: float
    ) -> Tuple[float, float]:
        if not self.points:
            return default_p_kw, default_q_kvar
        p, q = default_p_kw, default_q_kvar
        for t, pp, qq in self.points:
            if t_s >= t:
                p, q = pp, qq
            else:
                break
        return p, q

    @staticmethod
    def from_csv(path: str | Path) -> "LoadProfile":
        pts: List[Tuple[int, float, float]] = []
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                pts.append(
                    (
                        int(row["time_s"]),
                        float(row["P_load_kW"]),
                        float(row["Q_load_kVAr"]),
                    )
                )
        pts.sort(key=lambda x: x[0])
        return LoadProfile(points=pts)
