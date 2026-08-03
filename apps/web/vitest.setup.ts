import "@testing-library/jest-dom/vitest";

// jsdom implements none of these, and Radix primitives call them on mount: the Slider observes
// its track to position the thumb, and Select measures the trigger to place the popover.
// Without the stubs any component containing one throws on render, which reads as a failure in
// whatever is under test rather than a missing browser API.
if (!("ResizeObserver" in globalThis)) {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
}

if (!Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = () => false;
  Element.prototype.setPointerCapture = () => {};
  Element.prototype.releasePointerCapture = () => {};
}

if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}
