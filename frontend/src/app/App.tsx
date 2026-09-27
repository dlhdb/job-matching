import { NavLink, Route, Routes } from "react-router-dom";

import { CrawlPage } from "../crawl/CrawlPage";
import { DryRunIndicator } from "../dry-run/DryRunIndicator";
import { DryRunProvider } from "../dry-run/DryRunProvider";
import { JobTablePage } from "../job-database/JobTablePage";
import { ScoringIndicator } from "../scoring/ScoringIndicator";
import { ScoringProvider } from "../scoring/ScoringProvider";
import { useScoringExtension } from "../scoring/useScoringExtension";
import { SettingsPage } from "../settings/SettingsPage";
import { Placeholder } from "./Placeholder";

/** 外殼：頁首的導覽與評分、試跑的進度，以及各頁面；職缺表疊加評分的擴充 */
export function App() {
  return (
    <ScoringProvider>
      <DryRunProvider>
        <header>
          <h1>求職雷達</h1>
          <nav className="tabs" aria-label="頁面">
            <NavLink to="/" end>
              職缺表
            </NavLink>
            <NavLink to="/crawl">抓取</NavLink>
            <NavLink to="/settings">設定</NavLink>
          </nav>
          <ScoringIndicator />
          <DryRunIndicator />
        </header>
        <main>
          <Routes>
            <Route path="/" element={<JobTablePage useExtension={useScoringExtension} />} />
            <Route path="/crawl" element={<CrawlPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route
              path="*"
              element={<Placeholder title="找不到這一頁" message="網址沒有對應的頁面。" />}
            />
          </Routes>
        </main>
      </DryRunProvider>
    </ScoringProvider>
  );
}
