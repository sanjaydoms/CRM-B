import React, { useState } from 'react';
import { Menu, Search, Bell, X, User } from 'lucide-react';

/**
 * The phone header.
 *
 * It carries the hamburger itself rather than leaving it to the separate
 * .mobile-portal-header bar. Below 768px only one of the two headers is shown,
 * so whichever one is visible has to be the one that can reach the drawer --
 * otherwise the sidebar, and with it most of the app's navigation, becomes
 * unreachable on a phone.
 */

export function MobileHeader({ title, currentUser, notificationsCount, onOpenNotifications, onSearch, onOpenMenu }) {
  const [searchOpen, setSearchOpen] = useState(false);
  const [query, setQuery] = useState('');

  const handleSearchSubmit = (e) => {
    e.preventDefault();
    if (onSearch) onSearch(query);
  };

  return (
    <header className="mobile-app-header">
      {searchOpen ? (
        <form onSubmit={handleSearchSubmit} className="mobile-header-search-form">
          <input
            type="text"
            className="mobile-header-search-input"
            placeholder="Search orders, customers, designs…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            autoFocus
          />
          <button type="button" className="icon-btn-touch" onClick={() => setSearchOpen(false)}>
            <X size={20} />
          </button>
        </form>
      ) : (
        <div className="mobile-header-bar">
          <div className="mobile-header-brand-group">
            {onOpenMenu && (
              <button type="button" className="icon-btn-touch mobile-header-menu-btn"
                      onClick={onOpenMenu} aria-label="Open navigation menu">
                <Menu size={22} />
              </button>
            )}
            <h2 className="mobile-header-title">{title || 'Scaleezy'}</h2>
          </div>

          <div className="mobile-header-actions">
            <button type="button" className="icon-btn-touch" onClick={() => setSearchOpen(true)} aria-label="Search">
              <Search size={20} />
            </button>

            <button type="button" className="icon-btn-touch relative-btn" onClick={onOpenNotifications} aria-label="Notifications">
              <Bell size={20} />
              {notificationsCount > 0 && (
                <span className="mobile-header-badge">{notificationsCount}</span>
              )}
            </button>

            <div className="mobile-header-avatar">
              <img
                src={`https://api.dicebear.com/7.x/initials/svg?seed=${encodeURIComponent(currentUser?.first_name || 'User')}`}
                alt="Profile"
              />
            </div>
          </div>
        </div>
      )}
    </header>
  );
}
