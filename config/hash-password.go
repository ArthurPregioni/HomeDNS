// One-time password hashing utility. Password is accepted only on stdin.
package main

import (
	"fmt"
	"io"
	"os"

	"golang.org/x/crypto/bcrypt"
)

func main() {
	password, err := io.ReadAll(io.LimitReader(os.Stdin, 73))
	if err != nil || len(password) < 16 || len(password) > 72 {
		fmt.Fprintln(os.Stderr, "Invalid password input")
		os.Exit(1)
	}
	hash, err := bcrypt.GenerateFromPassword(password, 12)
	if err != nil {
		fmt.Fprintln(os.Stderr, "Password hashing failed")
		os.Exit(1)
	}
	fmt.Println(string(hash))
}
