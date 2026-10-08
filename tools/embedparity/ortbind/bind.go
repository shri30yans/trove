package ortbind

/*
#cgo CFLAGS: -I${SRCDIR}/../ort/include
#cgo LDFLAGS: -L${SRCDIR}/../ort/lib -lonnxruntime -Wl,-rpath,${SRCDIR}/../ort/lib
#include <stdlib.h>
#include "ort.h"
*/
import "C"
import (
	"fmt"
	"unsafe"
)

type Session struct {
	handle *C.OrtSessionHandle
}

func Init() error {
	if C.ort_init() != 0 {
		return fmt.Errorf("ort init: %s", C.GoString(C.ort_last_error()))
	}
	return nil
}

func Open(path string, threads int) (*Session, error) {
	cpath := C.CString(path)
	defer C.free(unsafe.Pointer(cpath))
	h := C.ort_open(cpath, C.int(threads))
	if h == nil {
		return nil, fmt.Errorf("open %s: %s", path, C.GoString(C.ort_last_error()))
	}
	return &Session{handle: h}, nil
}

func (s *Session) InputNames() []string {
	n := int(C.ort_input_count(s.handle))
	out := make([]string, n)
	for i := 0; i < n; i++ {
		out[i] = C.GoString(C.ort_input_name(s.handle, C.size_t(i)))
	}
	return out
}

func (s *Session) OutputNames() []string {
	n := int(C.ort_output_count(s.handle))
	out := make([]string, n)
	for i := 0; i < n; i++ {
		out[i] = C.GoString(C.ort_output_name(s.handle, C.size_t(i)))
	}
	return out
}

// RunText feeds the graph the three BERT inputs and returns last_hidden_state as [seq][768].
func (s *Session) RunText(inputIDs, tokenTypeIDs, attentionMask []int64) ([]float32, int, error) {
	seq := int64(len(inputIDs))
	need := seq * 768
	hidden := make([]float32, need)
	var written C.size_t
	rc := C.ort_run_text(s.handle,
		(*C.int64_t)(unsafe.Pointer(unsafe.SliceData(inputIDs))),
		(*C.int64_t)(unsafe.Pointer(unsafe.SliceData(tokenTypeIDs))),
		(*C.int64_t)(unsafe.Pointer(unsafe.SliceData(attentionMask))),
		C.int64_t(seq), (*C.float)(unsafe.Pointer(unsafe.SliceData(hidden))), C.size_t(need), &written)
	if rc != 0 {
		return nil, 0, fmt.Errorf("run text: %s", C.GoString(C.ort_last_error()))
	}
	return hidden, int(written), nil
}

func (s *Session) RunVision(pixels []float32) ([]float32, int, error) {
	need := int64(len(pixels))
	out := make([]float32, 197*768)
	var written C.size_t
	rc := C.ort_run_vision(s.handle,
		(*C.float)(unsafe.Pointer(unsafe.SliceData(pixels))), C.size_t(need),
		(*C.float)(unsafe.Pointer(unsafe.SliceData(out))), C.size_t(len(out)), &written)
	if rc != 0 {
		return nil, 0, fmt.Errorf("run vision: %s", C.GoString(C.ort_last_error()))
	}
	return out, int(written), nil
}
