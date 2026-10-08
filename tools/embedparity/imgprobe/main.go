package main

import (
	"encoding/binary"
	"encoding/json"
	"fmt"
	"image"
	"image/png"
	"math"
	"os"
	"probe/ortbind"
)

// CLIP-style preprocessing: antialiased Keys cubic (bicubic) resize to 224x224, /255, mean/std.
const (
	outSize = 224
	meanR   = 0.48145466
	meanG   = 0.4578275
	meanB   = 0.40821073
	stdR    = 0.26862954
	stdG    = 0.26130258
	stdB    = 0.27577711
)

// keysCubic is Pillow's "cubic" filter (Keys, a = -1/2), verified empirically
// against libImaging by reading the kernel response of a single-pixel upscale.
func keysCubic(x float64) float64 {
	x = math.Abs(x)
	if x <= 1 {
		return (1.5*x-2.5)*x*x + 1
	}
	if x < 2 {
		return ((-0.5*x+2.5)*x-4.0)*x + 2.0
	}
	return 0
}

// weights returns the tap offsets and normalised filter weights for one axis.
func weights(inCount, outCount int, support float64) []struct {
	indices []int
	w       []float64
} {
	scale := math.Max(float64(inCount)/float64(outCount), 1.0)
	radius := support * scale
	sigma := 1.0 / scale
	table := make([]struct {
		indices []int
		w       []float64
	}, outCount)
	for i := 0; i < outCount; i++ {
		center := (float64(i)+0.5)*scale - 0.5
		lo := int(math.Floor(center - radius))
		hi := int(math.Ceil(center + radius))
		if lo < 0 {
			lo = 0
		}
		if hi > inCount {
			hi = inCount
		}
		var sum float64
		for j := lo; j < hi; j++ {
			w := keysCubic((float64(j)-center)*sigma) * scale
			table[i].indices = append(table[i].indices, j)
			table[i].w = append(table[i].w, w)
			sum += w
		}
		if sum != 0 {
			for k := range table[i].w {
				table[i].w[k] /= sum
			}
		}
	}
	return table
}

// Resize matches Pillow's ImagingResample: horizontal pass to 224 (round to 8-bit),
// then vertical pass to 224 (round to 8-bit), then CLIP rescale/normalise.
func Resize(src image.Image) []float32 {
	b := src.Bounds()
	w, h := b.Dx(), b.Dy()
	xw := weights(w, outSize, 2.0)
	yw := weights(h, outSize, 2.0)
	plane := make([][]uint8, 3)
	for c := range plane {
		plane[c] = make([]uint8, h*outSize)
	}
	for c := 0; c < 3; c++ {
		for y := 0; y < h; y++ {
			dst := plane[c][y*outSize : (y+1)*outSize]
			for ox := 0; ox < outSize; ox++ {
				col := xw[ox]
				var acc float64
				for k, sx := range col.indices {
					r, g, bl, _ := src.At(b.Min.X+sx, b.Min.Y+y).RGBA()
					var v uint32
					switch c {
					case 0:
						v = r
					case 1:
						v = g
					default:
						v = bl
					}
					acc += float64(v>>8) * col.w[k]
				}
				dst[ox] = uint8(clamp(int(math.Round(acc)), 0, 255))
			}
		}
	}
	out := make([]float32, 3*outSize*outSize)
	for c := 0; c < 3; c++ {
		base := c * outSize * outSize
		for ox := 0; ox < outSize; ox++ {
			for oy := 0; oy < outSize; oy++ {
				row := yw[oy]
				var acc float64
				for k, sy := range row.indices {
					acc += float64(plane[c][sy*outSize+ox]) * row.w[k]
				}
				v := float64(clamp(int(math.Round(acc)), 0, 255)) / 255.0
				var m, sd float64
				switch c {
				case 0:
					m, sd = meanR, stdR
				case 1:
					m, sd = meanG, stdG
				default:
					m, sd = meanB, stdB
				}
				out[base+oy*outSize+ox] = float32((v - m) / sd)
			}
		}
	}
	return out
}

func clamp(v, lo, hi int) int {
	if v < lo {
		return lo
	}
	if v > hi {
		return hi
	}
	return v
}

type goldenDoc struct {
	Image map[string][]float32 `json:"image"`
}

func main() {
	f, err := os.Open("/tmp/trove-embed-probe/golden.png")
	if err != nil {
		panic(err)
	}
	defer f.Close()
	img, err := png.Decode(f)
	if err != nil {
		panic(err)
	}
	produced := Resize(img)

	raw, _ := os.ReadFile("/tmp/trove-embed-probe/pixels_golden.f32")
	pyPixels := make([]float32, len(raw)/4)
	for i := range pyPixels {
		pyPixels[i] = math.Float32frombits(binary.LittleEndian.Uint32(raw[i*4:]))
	}
	var maxAbs float64
	var sumAbs float64
	worst := 0.0
	for i := range produced {
		d := math.Abs(float64(produced[i]) - float64(pyPixels[i]))
		sumAbs += d
		if d > maxAbs {
			maxAbs = d
		}
		_ = worst
	}
	os.WriteFile("/tmp/trove-embed-probe/pixels_go.f32", func() []byte { bb := make([]byte, len(produced)*4); for i, v := range produced { binary.LittleEndian.PutUint32(bb[i*4:], math.Float32bits(v)) }; return bb }(), 0644)
	fmt.Printf("PIXELS n=%d maxAbsDiff=%.6f (=%.3f of a 0-255 step) meanAbsDiff=%.8f\n", len(produced), maxAbs, maxAbs*255, sumAbs/float64(len(produced)))

	if err := ortbind.Init(); err != nil {
		panic(err)
	}
	vs, err := ortbind.Open("/tmp/trove-embed-probe/cache/models--nomic-ai--nomic-embed-vision-v1.5/snapshots/e3a725bce72db07ca4adb1d83da08903f3ee02f8/onnx/model_int8.onnx", 2)
	if err != nil {
		panic(err)
	}
	hidden, n, err := vs.RunVision(produced)
	if err != nil {
		panic(err)
	}
	_ = n
	cls := l2(hidden[:768])
	var g goldenDoc
	gb, _ := os.ReadFile("/tmp/trove-embed-probe/python_golden.json")
	json.Unmarshal(gb, &g)
	want := g.Image["golden.png"]
	dot, na, nb := 0.0, 0.0, 0.0
	maxE := 0.0
	for i := range cls {
		dd := math.Abs(float64(cls[i]) - float64(want[i]))
		if dd > maxE {
			maxE = dd
		}
		dot += float64(cls[i]) * float64(want[i])
		na += float64(cls[i]) * float64(cls[i])
		nb += float64(want[i]) * float64(want[i])
	}
	fmt.Printf("VISION go-preprocess vs python-preprocess embedding: cosine=%.10f maxAbsDiff=%.3e (hidden floats=%d)\n", dot/(math.Sqrt(na)*math.Sqrt(nb)), maxE, n)
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
