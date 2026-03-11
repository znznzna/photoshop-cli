/** UXP runtime globals that are available but not in standard lib typings */

declare function require(module: string): any;

declare const module: {
  exports: any;
};
