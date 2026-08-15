import { useEffect, useRef } from "react";
import i18n from "@/i18n";
import type { AttributionCumulativePoint } from "@/lib/api";
import { getChartTheme } from "@/lib/chart-theme";
import { getPnlColors } from "@/lib/pnl-colors";
import { echarts, CHART_GROUP, connectCharts } from "@/lib/echarts";
import { escapeHtml } from "@/lib/escapeHtml";
import { useThemeDark } from "@/lib/theme-store";

interface Props {
  data: AttributionCumulativePoint[];
  height?: number;
}

export function AttributionCumulativeChart({ data, height = 300 }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const dark = useThemeDark();

  useEffect(() => {
    if (!ref.current || data.length === 0) return;
    const t = getChartTheme();
    const pnl = getPnlColors();
    const chart = echarts.init(ref.current);
    chart.group = CHART_GROUP;
    connectCharts();

    const portfolioLabel = i18n.t("runDetail.attrPortfolio");
    const benchmarkLabel = i18n.t("runDetail.attrBenchmark");
    const activeLabel = i18n.t("runDetail.attrActive");
    const dates = data.map((d) => d.date);

    chart.setOption({
      backgroundColor: "transparent",
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "cross" },
        backgroundColor: t.tooltipBg,
        borderColor: t.tooltipBorder,
        textStyle: { color: t.tooltipText, fontSize: 11 },
        formatter: (raw: unknown) => {
          const params = raw as Array<{ dataIndex?: number }>;
          if (!Array.isArray(params) || !params.length) return "";
          const point = data[params[0].dataIndex ?? 0];
          if (!point) return "";
          const pct = (v: number) => `${v > 0 ? "+" : ""}${(v * 100).toFixed(2)}%`;
          return `<b>${escapeHtml(point.date)}</b>`
            + `<br/>${portfolioLabel}: <b>${pct(point.portfolio)}</b>`
            + `<br/>${benchmarkLabel}: <b>${pct(point.benchmark)}</b>`
            + `<br/>${activeLabel}: <b>${pct(point.active)}</b>`;
        },
      },
      legend: {
        data: [portfolioLabel, benchmarkLabel, activeLabel],
        textStyle: { color: t.textColor, fontSize: 11 },
        right: 60,
        top: 4,
      },
      toolbox: {
        feature: {
          saveAsImage: { title: "Save" },
          restore: { title: "Reset" },
        },
        right: 8,
        top: 0,
        iconStyle: { borderColor: t.textColor },
      },
      grid: { left: 8, right: 8, top: 36, bottom: 8, containLabel: true },
      xAxis: {
        type: "category",
        data: dates,
        axisLine: { lineStyle: { color: t.axisColor } },
        axisLabel: { color: t.textColor, fontSize: 10 },
      },
      yAxis: {
        type: "value",
        splitLine: { lineStyle: { color: t.gridColor } },
        axisLabel: { color: t.textColor, fontSize: 10, formatter: "{value}%" },
      },
      dataZoom: [{ type: "inside" }],
      series: [
        {
          name: portfolioLabel,
          type: "line",
          data: data.map((d) => +(d.portfolio * 100).toFixed(4)),
          smooth: false,
          symbol: "none",
          lineStyle: { color: t.infoColor, width: 2 },
        },
        {
          name: benchmarkLabel,
          type: "line",
          data: data.map((d) => +(d.benchmark * 100).toFixed(4)),
          smooth: false,
          symbol: "none",
          lineStyle: { color: t.textColor, width: 1.5 },
        },
        {
          name: activeLabel,
          type: "line",
          data: data.map((d) => +(d.active * 100).toFixed(4)),
          smooth: false,
          symbol: "none",
          lineStyle: { color: pnl.profit, width: 1.5, type: "dashed" },
        },
      ],
    });

    let resizeFrame: number | null = null;
    const ro = new ResizeObserver(() => {
      if (resizeFrame !== null) cancelAnimationFrame(resizeFrame);
      resizeFrame = requestAnimationFrame(() => {
        resizeFrame = null;
        chart.resize();
      });
    });
    ro.observe(ref.current!);
    return () => {
      ro.disconnect();
      if (resizeFrame !== null) cancelAnimationFrame(resizeFrame);
      chart.dispose();
    };
  }, [data, dark]);

  if (data.length === 0) {
    return <div className="text-muted-foreground text-sm p-4">{i18n.t("runDetail.attrNoFactor")}</div>;
  }
  return <div ref={ref} style={{ height }} />;
}
