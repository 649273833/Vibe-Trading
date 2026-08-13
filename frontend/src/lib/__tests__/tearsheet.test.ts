import {
  normalizeEquitySeries,
  computeMonthlyReturns,
  computeAnnualReturns,
  computeTopDrawdowns,
  toDrawdownZones,
  type NormalizedEquityPoint,
} from "../tearsheet";

function pt(time: string, equity: number, drawdown = 0): NormalizedEquityPoint {
  return { time, equity, drawdown };
}

describe("normalizeEquitySeries", () => {
  it("parses artifacts_equity_csv string rows into numbers", () => {
    const rows = [
      { timestamp: "2024-01-01 00:00:00", equity: "100.5", drawdown: "-0.01" },
      { timestamp: "2024-01-02 00:00:00", equity: "102", drawdown: "0" },
    ];
    const out = normalizeEquitySeries(rows);
    expect(out).toHaveLength(2);
    expect(out[0]).toEqual({ time: "2024-01-01 00:00:00", equity: 100.5, drawdown: -0.01 });
    expect(out[1]).toEqual({ time: "2024-01-02 00:00:00", equity: 102, drawdown: 0 });
  });

  it("accepts EquityPoint[] input", () => {
    const out = normalizeEquitySeries([
      { time: "2024-01-01", equity: 100, drawdown: 0 },
      { time: "2024-01-02", equity: "101.5", drawdown: "-0.02" },
    ]);
    expect(out).toHaveLength(2);
    expect(out[1].equity).toBe(101.5);
    expect(out[1].drawdown).toBe(-0.02);
  });

  it("drops rows with non-finite equity or missing time", () => {
    const rows = [
      { timestamp: "2024-01-01", equity: "100", drawdown: "0" },
      { timestamp: "2024-01-02", equity: "abc", drawdown: "0" },
      { timestamp: "2024-01-03", equity: "Infinity", drawdown: "0" },
      { timestamp: "", equity: "103", drawdown: "0" },
      { equity: "104", drawdown: "0" },
      { timestamp: "2024-01-05", equity: "105", drawdown: "0" },
    ];
    const out = normalizeEquitySeries(rows);
    expect(out.map((p) => p.time)).toEqual(["2024-01-01", "2024-01-05"]);
  });

  it("returns [] for empty/undefined/null input", () => {
    expect(normalizeEquitySeries([])).toEqual([]);
    expect(normalizeEquitySeries(undefined)).toEqual([]);
    expect(normalizeEquitySeries(null)).toEqual([]);
  });

  it("defensively sorts when first row's date is after last row's date", () => {
    const out = normalizeEquitySeries([
      { timestamp: "2024-01-03", equity: "103", drawdown: "0" },
      { timestamp: "2024-01-01", equity: "101", drawdown: "0" },
      { timestamp: "2024-01-02", equity: "102", drawdown: "0" },
    ]);
    expect(out.map((p) => p.time)).toEqual(["2024-01-01", "2024-01-02", "2024-01-03"]);
  });

  it("preserves input order when already chronological", () => {
    const out = normalizeEquitySeries([
      { timestamp: "2024-01-01", equity: "1", drawdown: "0" },
      { timestamp: "2024-01-02", equity: "2", drawdown: "0" },
    ]);
    expect(out.map((p) => p.equity)).toEqual([1, 2]);
  });
});

describe("computeMonthlyReturns", () => {
  it("computes a hand-computed 3-month series (first month base = first observation)", () => {
    const points = [
      pt("2024-01-15", 100),
      pt("2024-01-31", 110),
      pt("2024-02-29", 121),
      pt("2024-03-31", 114.95),
    ];
    const out = computeMonthlyReturns(points);
    expect(out).toHaveLength(3);
    // Jan: 110 / 100 - 1 = +10% (base is the series' first observation)
    expect(out[0]).toMatchObject({ year: 2024, month: 1 });
    expect(out[0].ret).toBeCloseTo(0.1, 10);
    // Feb: 121 / 110 - 1 = +10%
    expect(out[1].ret).toBeCloseTo(0.1, 10);
    // Mar: 114.95 / 121 - 1 = -5%
    expect(out[2].ret).toBeCloseTo(-0.05, 10);
  });

  it("emits null for a gap month between populated months and does not pad outside", () => {
    const points = [
      pt("2023-12-31", 100),
      pt("2024-01-31", 110),
      // Feb 2024 missing
      pt("2024-03-31", 120),
    ];
    const out = computeMonthlyReturns(points);
    // Dec-2023 .. Mar-2024 inclusive, no padding before/after
    expect(out.map((m) => `${m.year}-${m.month}`)).toEqual([
      "2023-12", "2024-1", "2024-2", "2024-3",
    ]);
    expect(out[0].ret).toBeCloseTo(0, 10); // 100 / first-obs 100 - 1
    expect(out[1].ret).toBeCloseTo(0.1, 10); // 110 / 100 - 1
    expect(out[2].ret).toBeNull(); // gap month
    expect(out[3].ret).toBeNull(); // prior calendar month has no data
  });

  it("emits null when base equity is <= 0", () => {
    const points = [
      pt("2024-01-15", 0),
      pt("2024-01-31", 10),
      pt("2024-02-28", 12),
    ];
    const out = computeMonthlyReturns(points);
    expect(out[0].ret).toBeNull(); // base = first observation = 0
    expect(out[1].ret).toBeCloseTo(0.2, 10); // 12 / 10 - 1
  });

  it("returns [] for empty input", () => {
    expect(computeMonthlyReturns([])).toEqual([]);
  });
});

describe("computeAnnualReturns", () => {
  it("computes a hand-computed 2-year series (first year base = first observation)", () => {
    const points = [
      pt("2023-06-01", 100),
      pt("2023-12-31", 120),
      pt("2024-12-31", 150),
    ];
    const out = computeAnnualReturns(points);
    expect(out).toHaveLength(2);
    expect(out[0]).toMatchObject({ year: 2023 });
    expect(out[0].ret).toBeCloseTo(0.2, 10); // 120 / first-obs 100 - 1
    expect(out[1]).toMatchObject({ year: 2024 });
    expect(out[1].ret).toBeCloseTo(0.25, 10); // 150 / 120 - 1
  });

  it("skips years whose prior calendar year has no data", () => {
    const points = [
      pt("2022-12-31", 100),
      // 2023 missing entirely
      pt("2024-12-31", 150),
    ];
    const out = computeAnnualReturns(points);
    expect(out).toHaveLength(1);
    expect(out[0]).toMatchObject({ year: 2022 });
    expect(out[0].ret).toBeCloseTo(0, 10);
  });

  it("returns [] for empty input", () => {
    expect(computeAnnualReturns([])).toEqual([]);
  });
});

describe("computeTopDrawdowns", () => {
  it("detects two known episodes sorted deepest first", () => {
    const points = [
      pt("2024-01-01", 100),
      pt("2024-01-02", 120),
      pt("2024-01-03", 90),
      pt("2024-01-04", 130),
      pt("2024-01-05", 100),
      pt("2024-01-06", 140),
    ];
    const out = computeTopDrawdowns(points, 5);
    expect(out).toHaveLength(2);
    // Deepest: peak 120 -> trough 90 = -25%
    expect(out[0].peakTime).toBe("2024-01-02");
    expect(out[0].troughTime).toBe("2024-01-03");
    expect(out[0].recoveryTime).toBe("2024-01-04");
    expect(out[0].depth).toBeCloseTo(-0.25, 10);
    expect(out[0].peakToTroughDays).toBe(1);
    expect(out[0].troughToRecoveryDays).toBe(1);
    // Second: peak 130 -> trough 100 = -23.08%
    expect(out[1].peakTime).toBe("2024-01-04");
    expect(out[1].troughTime).toBe("2024-01-05");
    expect(out[1].recoveryTime).toBe("2024-01-06");
    expect(out[1].depth).toBeCloseTo(100 / 130 - 1, 10);
  });

  it("leaves recoveryTime null for a final unrecovered episode", () => {
    const points = [pt("2024-01-01", 100), pt("2024-01-02", 80)];
    const out = computeTopDrawdowns(points, 5);
    expect(out).toHaveLength(1);
    expect(out[0].peakTime).toBe("2024-01-01");
    expect(out[0].troughTime).toBe("2024-01-02");
    expect(out[0].recoveryTime).toBeNull();
    expect(out[0].depth).toBeCloseTo(-0.2, 10);
    expect(out[0].peakToTroughDays).toBe(1);
    expect(out[0].troughToRecoveryDays).toBeNull();
  });

  it("respects the n limit", () => {
    const points = [
      pt("2024-01-01", 100), pt("2024-01-02", 90), pt("2024-01-03", 110),
      pt("2024-01-04", 80), pt("2024-01-05", 120),
      pt("2024-01-06", 70), pt("2024-01-07", 130),
    ];
    const out = computeTopDrawdowns(points, 2);
    expect(out).toHaveLength(2);
    expect(out[0].depth).toBeLessThanOrEqual(out[1].depth);
  });

  it("returns null day spans when times cannot be parsed", () => {
    const points = [pt("not-a-date", 100), pt("also-bad", 80)];
    const out = computeTopDrawdowns(points, 5);
    expect(out).toHaveLength(1);
    expect(out[0].peakToTroughDays).toBeNull();
    expect(out[0].troughToRecoveryDays).toBeNull();
  });

  it("returns [] for empty or single-point input", () => {
    expect(computeTopDrawdowns([], 5)).toEqual([]);
    expect(computeTopDrawdowns([pt("2024-01-01", 100)], 5)).toEqual([]);
  });
});

describe("toDrawdownZones", () => {
  it("maps episodes to zones, falling back to lastTime when unrecovered", () => {
    const episodes = computeTopDrawdowns([
      pt("2024-01-01", 100),
      pt("2024-01-02", 90),
      pt("2024-01-03", 110),
      pt("2024-01-04", 80),
    ], 5);
    expect(episodes).toHaveLength(2);
    const zones = toDrawdownZones(episodes, "2024-01-04");
    expect(zones).toHaveLength(2);
    expect(zones[0].rank).toBe(1);
    expect(zones[1].rank).toBe(2);
    for (const z of zones) {
      expect(z.startTime).toBeTruthy();
      expect(z.endTime).toBeTruthy();
    }
    // The unrecovered episode must end at lastTime
    const unrecovered = episodes.find((e) => e.recoveryTime === null);
    expect(unrecovered).toBeDefined();
    const zone = zones[episodes.indexOf(unrecovered!)];
    expect(zone.endTime).toBe("2024-01-04");
    // The recovered episode keeps its recovery time
    const recovered = episodes.find((e) => e.recoveryTime !== null);
    if (recovered) {
      const z = zones[episodes.indexOf(recovered)];
      expect(z.endTime).toBe(recovered.recoveryTime);
    }
  });

  it("returns [] for no episodes", () => {
    expect(toDrawdownZones([], "2024-01-01")).toEqual([]);
  });
});
