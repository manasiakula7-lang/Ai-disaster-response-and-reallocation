import React from "react";

// Small stroke icons (24px grid), drawn inline so there is nothing extra to install.
const PATHS = {
  overview: "M3 13h8V3H3zM13 21h8V11h-8zM3 21h8v-6H3zM13 3v6h8V3z",
  alerts: "M12 3 2 20h20L12 3zM12 10v4M12 17.5v.01",
  results: "M4 20V10M10 20V4M16 20v-7M22 20H2",
  simulate: "M6 4l14 8-14 8z",
  whatif: "M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0M14 4v4M8 10v4M16 16v4",
  help: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM9.1 9a3 3 0 0 1 5.8 1c0 2-3 2.5-3 4.5M12 17.5v.01",
  sun: "M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10zM12 1v2M12 21v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M1 12h2M21 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4",
  moon: "M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z",
  play: "M7 4l13 8-13 8z",
  pause: "M7 4h4v16H7zM14 4h4v16h-4z",
  layers: "M12 2 2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5",
  people: "M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM23 21v-2a4 4 0 0 0-3-3.9M16 3.1a4 4 0 0 1 0 7.8",
  flame: "M12 22c4 0 7-3 7-7 0-5-5-7-5-12-3 2-4 5-4 8-1-1-2-2-2-4-2 2-3 5-3 8 0 4 3 7 7 7z",
  truck: "M1 3h15v13H1zM16 8h4l3 3v5h-7zM5.5 21a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5zM18.5 21a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5z",
  close: "M18 6 6 18M6 6l12 12",
  logo: "M2 12h4l3-8 4 16 3-8h6",
  map: "M1 6v16l7-4 8 4 7-4V2l-7 4-8-4-7 4zM8 2v16M16 6v16",
  network: "M12 5a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM5 21a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM19 21a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM11 4.5 6 17.5M13 4.5l5 13M7 19h10",
  shield: "M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10zM9 12l2 2 4-4",
  chart: "M3 21h18M6 17V9M11 17V5M16 17v-6M21 17V8",
  pulse: "M2 12h4l3-8 4 16 3-8h6",
  home: "M3 10.5 12 3l9 7.5M5 9v12h14V9M10 21v-6h4v6",
  pin: "M12 22s7-6.5 7-12a7 7 0 1 0-14 0c0 5.5 7 12 7 12zM12 12.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5z",
  arrow: "M5 12h14M13 6l6 6-6 6",
  tweet: "M21 5.5a8 8 0 0 1-2.3.6 4 4 0 0 0 1.8-2.2 8 8 0 0 1-2.5 1A4 4 0 0 0 11 8.6 11.4 11.4 0 0 1 2.7 4.4a4 4 0 0 0 1.2 5.4 4 4 0 0 1-1.8-.5 4 4 0 0 0 3.2 4 4 4 0 0 1-1.8.1 4 4 0 0 0 3.8 2.8A8 8 0 0 1 1.5 18a11.4 11.4 0 0 0 6.2 1.8c7.4 0 11.5-6.2 11.5-11.5v-.5A8 8 0 0 0 21 5.5z",
  road: "M5 21 9 3M19 21 15 3M12 4v3M12 10v4M12 17v3",
};

export default function Icon({ name, size = 18, ...rest }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...rest}>
      <path d={PATHS[name]} />
    </svg>
  );
}
