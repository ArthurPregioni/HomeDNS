// Google Play Termux's linker wrapper duplicates argv[0] for pure-Go binaries.
// Normalize that exact case before AdGuard Home parses its command line.
package main

import (
	"os"
	"runtime"
)

func init() {
	if runtime.GOOS == "android" && len(os.Args) > 1 && os.Args[0] == os.Args[1] {
		os.Args = append(os.Args[:1], os.Args[2:]...)
	}
}
