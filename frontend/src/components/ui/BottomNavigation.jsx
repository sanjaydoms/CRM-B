import React from 'react';

export function BottomNavigation({ tabs, activeTab, onChangeTab, onOpenMore }) {
  return (
    <nav className="mobile-bottom-nav">
      {tabs.map((tab) => {
        const Icon = tab.icon;
        const isActive = activeTab === tab.key;
        return (
          <button
            key={tab.key}
            type="button"
            className={`mobile-bottom-nav-item ${isActive ? 'active' : ''}`}
            onClick={() => {
              if (tab.key === 'more') {
                if (onOpenMore) onOpenMore();
              } else {
                onChangeTab(tab.key);
              }
            }}
          >
            <Icon size={20} />
            <span className="bottom-nav-label">{tab.label}</span>
          </button>
        );
      })}
    </nav>
  );
}
