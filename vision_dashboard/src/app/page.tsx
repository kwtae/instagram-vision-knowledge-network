"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";

interface DBItem {
  id: string;
  filepath: string;
  url: string;
  description: string;
  tags: string;
  type: string;
  search_score?: number;
}

export default function Home() {
  const [items, setItems] = useState<DBItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [activeTag, setActiveTag] = useState<string>("");
  const [searchQuery, setSearchQuery] = useState("");
  const [viewMode, setViewMode] = useState<"grid" | "list">("grid");
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(true);

  const LIMIT = 24;

  const coreTags = [
    "공간디자인", "실내건축", "가구", "조명",
    "상업공간", "주거공간", "건축모형", "도면"
  ];

  const fetchItems = useCallback(async (isLoadMore = false) => {
    if (isLoadMore) setLoadingMore(true);
    else setLoading(true);

    try {
      const currentOffset = isLoadMore ? offset + LIMIT : 0;
      let url = `/api/items?limit=${LIMIT}&offset=${currentOffset}`;

      if (searchQuery) {
        url += `&q=${encodeURIComponent(searchQuery)}`;
      } else if (activeTag) {
        url += `&tag=${encodeURIComponent(activeTag)}`;
      }

      const res = await fetch(url);
      const json = await res.json();

      if (json.success) {
        const newItems = json.data;
        if (isLoadMore) {
          setItems(prev => [...prev, ...newItems]);
          setOffset(currentOffset);
        } else {
          setItems(newItems);
          setOffset(0);
        }
        setHasMore(newItems.length === LIMIT);
      }
    } catch (e) {
      console.error("Fetch failed:", e);
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  }, [activeTag, searchQuery, offset]);

  // Initial fetch/reset
  useEffect(() => {
    fetchItems(false);
  }, [activeTag, searchQuery]);

  // Infinite Scroll Observer
  useEffect(() => {
    const observer = new IntersectionObserver((entries) => {
      if (entries[0].isIntersecting && hasMore && !loading && !loadingMore) {
        fetchItems(true);
      }
    }, { threshold: 0.1 });

    const target = document.querySelector("#scroll-sentinel");
    if (target) observer.observe(target);

    return () => observer.disconnect();
  }, [hasMore, loading, loadingMore, fetchItems]);

  return (
    <div className="container">
      <div className="header-section">
        <div className="header-top">
          <div className="header-title">
            <h1>Vision Knowledge Archive</h1>
            <p style={{ color: 'var(--text-secondary)', marginTop: '0.5rem' }}>Architectural Intelligence & Visual Discovery</p>
          </div>
          <Link href="/graph" style={{
            padding: "12px 24px",
            background: "white",
            color: "black",
            borderRadius: "12px",
            fontSize: "0.9rem",
            textDecoration: "none",
            fontWeight: 600,
            display: "flex",
            alignItems: "center",
            gap: "8px",
            boxShadow: "0 4px 15px rgba(255,255,255,0.1)"
          }}>
            🌌 Explore Neural Nebula
          </Link>
        </div>

        <div className="search-container">
          <input
            type="text"
            className="search-input"
            placeholder="Search anything (e.g. 'modern living room with concrete walls')..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>
      </div>

      <div className="controls-bar">
        <div className="filter-bar">
          <button
            className={`filter-btn ${activeTag === "" ? 'active' : ''}`}
            onClick={() => { setActiveTag(""); setSearchQuery(""); }}
          >
            All
          </button>
          {coreTags.map(tag => (
            <button
              key={tag}
              className={`filter-btn ${activeTag === tag ? 'active' : ''}`}
              onClick={() => { setActiveTag(tag); setSearchQuery(""); }}
            >
              {tag}
            </button>
          ))}
        </div>

        <div className="view-toggle">
          <button
            className={`toggle-btn ${viewMode === 'grid' ? 'active' : ''}`}
            onClick={() => setViewMode('grid')}
          >
            Grid
          </button>
          <button
            className={`toggle-btn ${viewMode === 'list' ? 'active' : ''}`}
            onClick={() => setViewMode('list')}
          >
            List
          </button>
        </div>
      </div>

      {loading && !items.length ? (
        <div className="loader">Analyzing multidimensional vectors...</div>
      ) : (
        <>
          <div className={viewMode === 'grid' ? 'masonry-grid' : 'list-view'}>
            {items.map(item => (
              viewMode === 'grid' ? (
                <a
                  key={item.id}
                  href={`/api/image?path=${encodeURIComponent(item.filepath)}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="masonry-item"
                  style={{ textDecoration: 'none', color: 'inherit', display: 'block' }}
                >
                  {item.search_score && <div className="score-badge">{Math.round(item.search_score * 100)}% Match</div>}
                  <div className="item-image-container">
                    <img
                      src={`/api/image?path=${encodeURIComponent(item.filepath)}&w=600`}
                      alt="archive item"
                      className="item-image"
                      loading="lazy"
                    />
                  </div>
                  <div className="item-content">
                    <pre>{item.description.replace('Vision Description:\n', '')}</pre>
                    <div className="tag-list">
                      {item.tags.split(',').slice(0, 4).map(tag => {
                        const t = tag.trim();
                        if (!t) return null;
                        return <span key={t} className="tag">{t}</span>;
                      })}
                    </div>
                  </div>
                </a>
              ) : (
                <a
                  key={item.id}
                  href={`/api/image?path=${encodeURIComponent(item.filepath)}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="list-item"
                  style={{ textDecoration: 'none', color: 'inherit' }}
                >
                  <img
                    src={`/api/image?path=${encodeURIComponent(item.filepath)}&w=200`}
                    alt="thumb"
                    className="list-thumb"
                  />
                  <div className="list-info">
                    <h3>{item.filepath.split('\\').pop()?.split('/').pop()}</h3>
                    <p>{item.description.substring(0, 150)}...</p>
                    <div className="tag-list" style={{ marginTop: '8px' }}>
                      {item.tags.split(',').slice(0, 5).map(t => (
                        <span key={t} className="tag">{t.trim()}</span>
                      ))}
                    </div>
                  </div>
                  {item.search_score && <div style={{ color: '#00e5ff', fontWeight: 600, fontSize: '0.8rem' }}>{Math.round(item.search_score * 100)}%</div>}
                </a>
              )
            ))}
          </div>

          <div id="scroll-sentinel" style={{ height: "100px", display: "flex", alignItems: "center", justifyContent: "center" }}>
            {loadingMore && <div className="loader">Summoning more artifacts...</div>}
            {!hasMore && items.length > 0 && <div className="loader" style={{ opacity: 0.5 }}>End of Archive.</div>}
          </div>

          {items.length === 0 && !loading && (
            <div className="loader">No dimensions found matching your query.</div>
          )}
        </>
      )}
    </div>
  );
}
