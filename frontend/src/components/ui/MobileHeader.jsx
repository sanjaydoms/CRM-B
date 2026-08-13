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

// The search affordance is gone: `onSearch` had no caller anywhere in the
// application, so tapping the magnifier on a phone opened a full-width field,
// took the keyboard, accepted a query and did nothing with it -- on the header
// that sits above every screen. Deleted rather than wired up, because there is
// no cross-entity search endpoint to wire it to; the Orders, Customers and
// Invoices screens each have their own working search box.
export function MobileHeader({ title, currentUser, notificationsCount, onOpenNotifications, onOpenMenu }) {
  return (
    <header className="mobile-app-header">
      {(
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
