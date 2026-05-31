"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";

const AXIS = { fontSize: 12, fill: "#5b6678" };
const GRID = "#e2e6ee";

export function HBar({
  data,
  dataKey,
  categoryKey,
  color = "#4338ca",
  height = 320,
  unit = "",
}: {
  data: any[];
  dataKey: string;
  categoryKey: string;
  color?: string;
  height?: number;
  unit?: string;
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} layout="vertical" margin={{ left: 8, right: 16, top: 4, bottom: 4 }}>
        <CartesianGrid stroke={GRID} horizontal={false} />
        <XAxis type="number" tick={AXIS} stroke={GRID} />
        <YAxis type="category" dataKey={categoryKey} tick={AXIS} stroke={GRID} width={150} />
        <Tooltip formatter={(v: any) => `${v}${unit}`} contentStyle={{ fontSize: 13, borderRadius: 8 }} />
        <Bar dataKey={dataKey} fill={color} radius={[0, 4, 4, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

export function HBarColored({
  data,
  dataKey,
  categoryKey,
  colorKey,
  height = 320,
}: {
  data: any[];
  dataKey: string;
  categoryKey: string;
  colorKey: string;
  height?: number;
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} layout="vertical" margin={{ left: 8, right: 16, top: 4, bottom: 4 }}>
        <CartesianGrid stroke={GRID} horizontal={false} />
        <XAxis type="number" tick={AXIS} stroke={GRID} />
        <YAxis type="category" dataKey={categoryKey} tick={AXIS} stroke={GRID} width={150} />
        <Tooltip contentStyle={{ fontSize: 13, borderRadius: 8 }} />
        <Bar dataKey={dataKey} radius={[0, 4, 4, 0]}>
          {data.map((d, i) => (
            <Cell key={i} fill={d[colorKey]} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export function Donut({
  data,
  height = 260,
}: {
  data: { name: string; value: number; color: string }[];
  height?: number;
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <PieChart>
        <Pie data={data} dataKey="value" nameKey="name" innerRadius={60} outerRadius={95} paddingAngle={2}>
          {data.map((d, i) => (
            <Cell key={i} fill={d.color} />
          ))}
        </Pie>
        <Tooltip contentStyle={{ fontSize: 13, borderRadius: 8 }} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
      </PieChart>
    </ResponsiveContainer>
  );
}

export function Scatter2D({
  data,
  xKey,
  yKey,
  xLabel,
  yLabel,
  nameKey = "name",
  height = 420,
  refDiagonal = false,
}: {
  data: any[];
  xKey: string;
  yKey: string;
  xLabel: string;
  yLabel: string;
  nameKey?: string;
  height?: number;
  refDiagonal?: boolean;
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ScatterChart margin={{ left: 8, right: 16, top: 8, bottom: 20 }}>
        <CartesianGrid stroke={GRID} />
        <XAxis
          type="number"
          dataKey={xKey}
          name={xLabel}
          tick={AXIS}
          stroke={GRID}
          label={{ value: xLabel, position: "insideBottom", offset: -10, fontSize: 12, fill: "#5b6678" }}
        />
        <YAxis
          type="number"
          dataKey={yKey}
          name={yLabel}
          tick={AXIS}
          stroke={GRID}
          label={{ value: yLabel, angle: -90, position: "insideLeft", fontSize: 12, fill: "#5b6678" }}
        />
        <ZAxis range={[60, 60]} />
        <Tooltip
          cursor={{ strokeDasharray: "3 3" }}
          contentStyle={{ fontSize: 13, borderRadius: 8 }}
          formatter={(v: any, n: any) => [typeof v === "number" ? v.toFixed(2) : v, n]}
          labelFormatter={() => ""}
        />
        <Scatter data={data} fill="#4338ca" fillOpacity={0.7} />
      </ScatterChart>
    </ResponsiveContainer>
  );
}

export function GroupedBar({
  data,
  categoryKey,
  series,
  height = 380,
}: {
  data: any[];
  categoryKey: string;
  series: { key: string; name: string; color: string }[];
  height?: number;
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} layout="vertical" margin={{ left: 8, right: 16, top: 4, bottom: 4 }}>
        <CartesianGrid stroke={GRID} horizontal={false} />
        <XAxis type="number" tick={AXIS} stroke={GRID} />
        <YAxis type="category" dataKey={categoryKey} tick={AXIS} stroke={GRID} width={150} />
        <Tooltip contentStyle={{ fontSize: 13, borderRadius: 8 }} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        {series.map((s) => (
          <Bar key={s.key} dataKey={s.key} name={s.name} fill={s.color} radius={[0, 3, 3, 0]} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}
