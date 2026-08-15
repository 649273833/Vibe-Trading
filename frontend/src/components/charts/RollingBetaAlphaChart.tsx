import { useEffect, useRef } from "react";
import i18n from "@/i18n";
import type { AttributionRollingPoint } from "@/lib/api";
import { getChartTheme } from "@/lib/chart-theme";
import { echarts, CHART_GROUP, connectCharts } from "@/lib/echarts";
import { escapeHtml } from "@/lib/escapeHtml";
import { useThemeDark } from "@/lib/theme-store";

interface Props {
  data: AttributionRollingPoint[];
  height?: number;
}

export function RollingBetaAlphaChart({ data, height = 280 }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const dark = useThemeDark();

  useEffect(() => {
    if (!ref.current || data.length === 0) return;
    const t = getChartTheme();
    const chart = echarts.init(ref.current);
    chart.group = CHART_GROUP;
    connectCharts();

    const betaLabel = i18n.t("runDetail.attrBeta");
    const alphaLabel = i18n.t("runDetail.attrAlpha");
    const dates = data.map((d) => d.date);
    const betas = data.map((d) => +d.beta.toFixed(4));
    const alphas = data.map((d) => +(d.alpha_annualized * 100).toFixed(4));

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
          return `<b>${escapeHtml(point.date)}</b>`
            + `<br/>${betaLabel}: <b>${point.beta.toFixed(2)}</b>`
            + `<br/>${alphaLabel}: <b>${(point.alpha_annualized * 100).toFixed(2)}%</b>`;
        },
      },
      legend: {
        data: [betaLabel, alphaLabel],
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
      yAxis: [
        {
          type: "value",
          name: betaLabel,
          nameTextStyle: { color: t.textColor, fontSize: 10 },
          splitLine: { lineStyle: { color: t.gridColor } },
          axisLabel: { color: t.textColor, fontSize: 10 },
        },
        {
          type: "value",
          name: alphaLabel,
          nameTextStyle: { color: t.textColor, fontSize: 10 },
          splitLine: { show: false },
          axisLabel: { color: t.textColor, fontSize: 10, formatter: "{value}%" },
        },
      ],
      dataZoom: [{ type: "inside" }],
      series: [
        {
          name: betaLabel,
          type: "line",
          yAxisIndex: 0,
          data: betas,
          smooth: false,
          symbol: "none",
          lineStyle: { color: t.infoColor, width: 2 },
        },
        {
          name: alphaLabel,
          type: "line",
          yAxisIndex: 1,
          data: alphas,
          smooth: false,
          symbol: "none",
          lineStyle: { color: t.warningColor, width: 1.5 },
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
