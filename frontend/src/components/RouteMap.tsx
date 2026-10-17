import { useT } from "../lib/i18n";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
// MapLibre finds its worker next to its own file, which Vite relocates; bundle it explicitly.
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import { api } from "../lib/api";
import { Badge } from "./ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";

interface RouteLine {
  allocation_id: string; supplier_name: string; lat: number; lon: number; product_name: string; qty: number; status: string;
  planner_estimate_km: number | null;
  route: { source: "osrm" | "estimated"; distance_km: number | null; duration_min: number | null; geometry: { type: "LineString"; coordinates: [number, number][] } | null };
}
interface RoutesResponse { merchant: { name: string; lat: number; lon: number }; lines: RouteLine[]; attribution: string }

maplibregl.setWorkerUrl(workerUrl);

const STYLE = "https://tiles.openfreemap.org/styles/liberty"; // OpenFreeMap: free, no API key
const COLOURS = ["#5b35f2", "#ea580c", "#059669", "#0284c7", "#db2777"];

/** Map of the active plan: merchant, each supplier, and the road route where the routing
 *  service answered. Estimated legs are drawn dashed and labelled as estimates. */
export default function RouteMap({ orderId }: { orderId: string }) {
  const { t } = useT();
  const q = useQuery({ queryKey: ["routes", orderId], queryFn: () => api.get<RoutesResponse>(`/api/orders/${orderId}/routes`) });
  const el = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!q.data || !el.current) return;
    const { merchant, lines } = q.data;
    const map = new maplibregl.Map({ container: el.current, style: STYLE, center: [merchant.lon, merchant.lat], zoom: 11, attributionControl: { compact: true } });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    const bounds = new maplibregl.LngLatBounds([merchant.lon, merchant.lat], [merchant.lon, merchant.lat]);
    new maplibregl.Marker({ color: "#0f172a" }).setLngLat([merchant.lon, merchant.lat])
      .setPopup(new maplibregl.Popup().setText(`${merchant.name} (you)`)).addTo(map);
    lines.forEach((l, i) => {
      bounds.extend([l.lon, l.lat]);
      new maplibregl.Marker({ color: COLOURS[i % COLOURS.length] }).setLngLat([l.lon, l.lat])
        .setPopup(new maplibregl.Popup().setText(`${l.supplier_name}: ${l.qty} ${l.product_name} (${l.status.replace("_", " ")})`)).addTo(map);
    });
    map.on("load", () => {
      lines.forEach((l, i) => {
        const coords = l.route.geometry?.coordinates ?? [[l.lon, l.lat], [merchant.lon, merchant.lat]];
        coords.forEach((c) => bounds.extend(c));
        map.addSource(`r${i}`, { type: "geojson", data: { type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: coords } } });
        map.addLayer({ id: `r${i}`, type: "line", source: `r${i}`, layout: { "line-cap": "round" },
          paint: { "line-color": COLOURS[i % COLOURS.length], "line-width": 4, "line-opacity": 0.85, ...(l.route.geometry ? {} : { "line-dasharray": [2, 2] }) } });
      });
      map.fitBounds(bounds, { padding: 48, maxZoom: 13, duration: 0 });
    });
    return () => map.remove();
  }, [q.data]);

  if (q.isError) return null;
  return (
    <Card>
      <CardHeader><CardTitle>{t("order.routes")}</CardTitle></CardHeader>
      <CardContent className="space-y-3">
        <div ref={el} className="h-72 w-full overflow-hidden rounded-lg bg-slate-100 dark:bg-slate-800" role="region" aria-label="Map of supplier delivery routes" />
        <ul className="space-y-1 text-sm">
          {q.data?.lines.map((l) => (
            <li key={l.allocation_id} className="flex flex-wrap items-center gap-2">
              <span className="font-medium">{l.supplier_name}</span>
              <span className="tabular-nums text-slate-600 dark:text-slate-300">
                {l.route.distance_km ?? "—"} km{l.route.duration_min ? ` · ${Math.round(l.route.duration_min)} min` : ""}
              </span>
              <Badge variant={l.route.source === "osrm" ? "success" : "warning"}>{l.route.source === "osrm" ? "road route (OSRM)" : "straight-line estimate"}</Badge>
              {l.route.source === "osrm" && l.planner_estimate_km !== null && <span className="text-xs text-slate-500">planner estimate {l.planner_estimate_km} km</span>}
            </li>
          ))}
        </ul>
        <p className="text-[11px] text-slate-500">Map © OpenFreeMap, OpenMapTiles, OpenStreetMap contributors. {q.data?.attribution}. Plan costs use the labelled planner estimates.</p>
      </CardContent>
    </Card>
  );
}
