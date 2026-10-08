package main

import (
	"encoding/binary"
	"encoding/json"
	"fmt"
	"math"
	"os"
	"probe/ortbind"
)

type Golden struct {
	Text    map[string][]float32 `json:"text"`
	Image   map[string][]float32 `json:"image"`
	Tokens  Tokens               `json:"tokens"`
	PixelSh []int                `json:"pixel_shape"`
}

type Tokens struct {
	Text          string  `json:"text"`
	InputIDs      []int64 `json:"input_ids"`
	AttentionMask []int64 `json:"attention_mask"`
	TokenTypeIDs  []int64 `json:"token_type_ids"`
	SeqLen        int     `json:"seq_len"`
}

func load(path string, v any) {
	b, err := os.ReadFile(path)
	if err != nil {
		panic(err)
	}
	if err := json.Unmarshal(b, v); err != nil {
		panic(err)
	}
}

// poolText mirrors nomic_runtime.text_embedding: masked mean pool, standardise, L2 normalise.
func poolText(hidden []float32, seq int, mask []int64) []float32 {
	pooled := make([]float32, 768)
	var denom float32
	for _, m := range mask {
		denom += float32(m)
	}
	if denom < 1 {
		denom = 1
	}
	for t := 0; t < seq; t++ {
		m := float32(mask[t])
		for d := 0; d < 768; d++ {
			pooled[d] += hidden[t*768+d] * m
		}
	}
	for d := 0; d < 768; d++ {
		pooled[d] /= denom
	}
	var mean float64
	for d := 0; d < 768; d++ {
		mean += float64(pooled[d])
	}
	mean /= 768.0
	var sq float64
	centred := make([]float32, 768)
	for d := 0; d < 768; d++ {
		c := float32(float64(pooled[d]) - mean)
		centred[d] = c
		sq += float64(c) * float64(c)
	}
	scale := float32(math.Sqrt(sq/768.0 + 1e-5))
	for d := 0; d < 768; d++ {
		centred[d] = centred[d] / scale
	}
	return l2(centred)
}

func l2(v []float32) []float32 {
	var sq float64
	for _, x := range v {
		sq += float64(x) * float64(x)
	}
	norm := float32(math.Sqrt(sq))
	out := make([]float32, len(v))
	for i, x := range v {
		out[i] = x / norm
	}
	return out
}

func compare(a, b []float32) (maxAbs, cosine float64) {
	var dot, na, nb float64
	maxAbs = 0
	for i := range a {
		d := math.Abs(float64(a[i]) - float64(b[i]))
		if d > maxAbs {
			maxAbs = d
		}
		dot += float64(a[i]) * float64(b[i])
		na += float64(a[i]) * float64(a[i])
		nb += float64(b[i]) * float64(b[i])
	}
	return maxAbs, dot / (math.Sqrt(na) * math.Sqrt(nb))
}

func main() {
	var golden Golden
	load("/tmp/trove-embed-probe/python_golden.json", &golden)

	if err := ortbind.Init(); err != nil {
		fmt.Println("init failed:", err)
		os.Exit(1)
	}

	textPath := "/tmp/trove-embed-probe/cache/models--nomic-ai--nomic-embed-text-v1.5/snapshots/e9b6763023c676ca8431644204f50c2b100d9aab/onnx/model_int8.onnx"
	visionPath := "/tmp/trove-embed-probe/cache/models--nomic-ai--nomic-embed-vision-v1.5/snapshots/e3a725bce72db07ca4adb1d83da08903f3ee02f8/onnx/model_int8.onnx"

	ts, err := ortbind.Open(textPath, 2)
	if err != nil {
		fmt.Println("text open failed:", err)
		os.Exit(1)
	}
	fmt.Println("GO text inputs:", ts.InputNames(), "outputs:", ts.OutputNames())
	ids := golden.Tokens.InputIDs
	mask := golden.Tokens.AttentionMask
	types := golden.Tokens.TokenTypeIDs
	if types == nil {
		types = make([]int64, len(ids))
	}
	hidden, n, err := ts.RunText(ids, types, mask)
	if err != nil {
		fmt.Println("text run failed:", err)
		os.Exit(1)
	}
	fmt.Printf("text hidden floats=%d expected=%d\n", n, len(ids)*768)
	got := poolText(hidden[:n], len(ids), mask)
	want := golden.Text["query||trip to lisbon"]
	maxAbs, cos := compare(got, want)
	fmt.Printf("TEXT exact-input parity: maxAbsDiff=%.3e cosine=%.10f\n", maxAbs, cos)
	fmt.Printf("  go[:4] = %.6f %.6f %.6f %.6f\n", got[0], got[1], got[2], got[3])
	fmt.Printf("  py[:4] = %.6f %.6f %.6f %.6f\n", want[0], want[1], want[2], want[3])

	vs, err := ortbind.Open(visionPath, 2)
	if err != nil {
		fmt.Println("vision open failed:", err)
		os.Exit(1)
	}
	fmt.Println("GO vision inputs:", vs.InputNames(), "outputs:", vs.OutputNames())
	raw, err := os.ReadFile("/tmp/trove-embed-probe/pixels_golden.f32")
	if err != nil {
		fmt.Println("pixel file missing:", err)
		os.Exit(1)
	}
	pixels := make([]float32, len(raw)/4)
	for i := range pixels {
		pixels[i] = math.Float32frombits(binary.LittleEndian.Uint32(raw[i*4:]))
	}
	vh, vn, err := vs.RunVision(pixels)
	if err != nil {
		fmt.Println("vision run failed:", err)
		os.Exit(1)
	}
	cls := make([]float32, 768)
	copy(cls, vh[:768])
	vgot := l2(cls)
	vwant := golden.Image["golden.png"]
	vmax, vcos := compare(vgot, vwant)
	fmt.Printf("VISION exact-input parity: hidden=%d maxAbsDiff=%.3e cosine=%.10f\n", vn, vmax, vcos)
	fmt.Printf("  go[:4] = %.6f %.6f %.6f %.6f\n", vgot[0], vgot[1], vgot[2], vgot[3])
	fmt.Printf("  py[:4] = %.6f %.6f %.6f %.6f\n", vwant[0], vwant[1], vwant[2], vwant[3])
}
