// Go port of lexell/bench/pingpong.lxl: two goroutines pass a counter back and forth
// 2,000,000 times over unbuffered channels; the same checksum line.
package main

import "fmt"

func main() {
	n := int64(2000000)
	toPong := make(chan int64)
	toPing := make(chan int64)
	done := make(chan int64)
	go func() {
		count := int64(0)
		for {
			m := <-toPong
			if m < 0 {
				done <- count
				return
			}
			toPing <- m + 1
			count++
		}
	}()
	total := int64(0)
	for i := int64(0); i < n; i++ {
		toPong <- i * 2
		total += <-toPing
	}
	toPong <- -1
	fmt.Printf("%d %d\n", total, <-done)
}
