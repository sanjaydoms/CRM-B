/** Does this fabric answer to a colour the customer asked for?
 *
 *  Two ways of asking, one function. A word ("maroon", "blue") is matched
 *  against the colour name the boutique gave the roll, as a substring, so
 *  "blue" finds "Aqua Blue". A hex ("#7a1f2b", from the colour wheel) is
 *  matched against the roll's recorded shade by distance, because nobody will
 *  land the wheel on a roll's exact hex, and "near enough to the same colour"
 *  is what they meant.
 *
 *  ponytail: straight RGB distance, not a perceptual space. Good enough to tell
 *  maroon from navy; swap for CIELAB if the boutique complains that two
 *  greens it can tell apart are being lumped together.
 */

const HEX = /^#([0-9a-f]{6})$/i;
const NEAR = 90;   // out of ~441: same colour family, not the same roll

const rgb = (hex) => {
  const m = HEX.exec((hex || '').trim());
  if (!m) return null;
  const n = parseInt(m[1], 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
};

const distance = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);

export const isHexQuery = (query) => HEX.test((query || '').trim());

export const fabricMatchesColour = (fabric, query) => {
  const q = (query || '').trim();
  if (!q) return true;
  const wanted = rgb(q);
  if (wanted) {
    const have = rgb(fabric.color_hex);
    return Boolean(have) && distance(wanted, have) <= NEAR;
  }
  return (fabric.color || '').toLowerCase().includes(q.toLowerCase());
};
