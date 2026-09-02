/**
 * The Android back button, and the stack of things it can close.
 *
 * On the web, "back" is browser history. This app has none: it is one component
 * whose screen is a state variable, so the hardware back button had nothing to
 * act on and Android's default took over -- which is to close the application.
 * A tailor with a bottom sheet open pressed back and the app exited, losing
 * whatever they had typed.
 *
 * Handlers are a stack because that is what the screen is: a dashboard, with a
 * detail over it, with a sheet over that. Back closes the topmost thing that
 * says it can be closed, and only when nothing can does it fall through to
 * leaving the app.
 *
 * A handler returns true when it handled the press.
 */

const handlers = [];

/** Register a handler; returns the function that removes it again. */
export const onBack = (handler) => {
  handlers.push(handler);
  return () => {
    const index = handlers.lastIndexOf(handler);
    if (index >= 0) handlers.splice(index, 1);
  };
};

/** Run the stack from the top. True when something handled the press. */
export const runBack = () => {
  for (let i = handlers.length - 1; i >= 0; i -= 1) {
    try {
      if (handlers[i]()) return true;
    } catch (error) {
      // A throwing handler must not make the back button dead for the ones
      // below it.
      console.error('back handler failed', error);
    }
  }
  return false;
};
