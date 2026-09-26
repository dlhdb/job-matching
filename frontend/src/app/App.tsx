import { NavLink, Route, Routes } from "react-router-dom";

import { CrawlPage } from "../crawl/CrawlPage";
import { JobTablePage } from "../job-database/JobTablePage";
import { SettingsPage } from "../settings/SettingsPage";
import { Placeholder } from "./Placeholder";

/** 外殼：頁首的導覽與各頁面 */
export function App() {
  return (
    <>
      <header>
        <h1>求職雷達</h1>
        <nav className="tabs" aria-label="頁面">
          <NavLink to="/" end>
            職缺表
          </NavLink>
          <NavLink to="/crawl">抓取</NavLink>
          <NavLink to="/settings">設定</NavLink>
        </nav>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<JobTablePage />} />
          <Route path="/crawl" element={<CrawlPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route
            path="*"
            element={<Placeholder title="找不到這一頁" message="網址沒有對應的頁面。" />}
          />
        </Routes>
      </main>
    </>
  );
}
