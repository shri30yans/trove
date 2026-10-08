package main

import (
	"encoding/json"
	"fmt"
	"os"
	"strings"
	"unicode"

	"golang.org/x/text/unicode/norm"
)

// WordPiece tokenizer reproducing HF's BertNormalizer + BertPreTokenizer + WordPiece model
// + [CLS]/[SEP] post-processing, driven by the same tokenizer.json the Python path loads.

type TokJSON struct {
	AddedTokens []struct {
		Content       string `json:"content"`
		ID            int    `json:"id"`
		Special       bool   `json:"special"`
	} `json:"added_tokens"`
	Normalizer struct {
		Type               string `json:"type"`
		CleanText          bool   `json:"clean_text"`
		HandleChinese      bool   `json:"handle_chinese_chars"`
		StripAccents       *bool  `json:"strip_accents"`
		Lowercase          bool   `json:"lowercase"`
	} `json:"normalizer"`
	Model struct {
		Type                     string         `json:"type"`
		UnkToken                 string         `json:"unk_token"`
		ContinuingSubwordPrefix  string         `json:"continuing_subword_prefix"`
		MaxInputCharsPerWord     int            `json:"max_input_chars_per_word"`
		Vocab                    map[string]int `json:"vocab"`
	} `json:"model"`
	PostProcessor struct {
		Type   string `json:"type"`
		Single []struct {
			SpecialToken *struct {
				ID     string `json:"id"`
				TypeID int    `json:"type_id"`
			} `json:"SpecialToken,omitempty"`
			Sequence *struct {
				ID     string `json:"id"`
				TypeID int    `json:"type_id"`
			} `json:"Sequence,omitempty"`
		} `json:"single"`
	} `json:"post_processor"`
}

type Tokenizer struct {
	vocab        map[string]int
	unk          string
	continuing   string
	maxWordChars int
	specials     map[string]int
	cls          string
	sep          string
	lowercase    bool
	stripAccents bool
	cleanText    bool
	handleChinese bool
}

func LoadTokenizer(path string) (*Tokenizer, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var t TokJSON
	if err := json.Unmarshal(raw, &t); err != nil {
		return nil, err
	}
	tz := &Tokenizer{
		vocab: t.Model.Vocab, unk: t.Model.UnkToken,
		continuing: t.Model.ContinuingSubwordPrefix,
		maxWordChars: t.Model.MaxInputCharsPerWord,
		specials: map[string]int{}, lowercase: t.Normalizer.Lowercase,
		stripAccents: t.Normalizer.Lowercase, cleanText: t.Normalizer.CleanText,
		handleChinese: t.Normalizer.HandleChinese,
	}
	if t.Normalizer.StripAccents != nil {
		tz.stripAccents = *t.Normalizer.StripAccents
	}
	for _, a := range t.AddedTokens {
		tz.specials[a.Content] = a.ID
	}
	for _, item := range t.PostProcessor.Single {
		if item.SpecialToken != nil {
			if tz.cls == "" {
				tz.cls = item.SpecialToken.ID
			} else {
				tz.sep = item.SpecialToken.ID
			}
		}
	}
	return tz, nil
}

func isCJK(r rune) bool {
	return (r >= 0x4E00 && r <= 0x9FFF) || (r >= 0x3400 && r <= 0x4DBF) ||
		(r >= 0x20000 && r <= 0x2A6DF) || (r >= 0xF900 && r <= 0xFAFF) ||
		(r >= 0x2F800 && r <= 0x2FA1F)
}

func isPunct(r rune) bool {
	// Rust BertPreTokenizer separates anything in Unicode categories P* or S*.
	// '_' is Pc (connector punctuation), so it IS a boundary.
	if unicode.IsLetter(r) || unicode.IsNumber(r) {
		return false
	}
	return !unicode.IsSpace(r)
}

func (tz *Tokenizer) normalize(s string) string {
	var b strings.Builder
	for _, r := range s {
		if tz.cleanText && (unicode.IsControl(r) || r == '\uFFFE' || r == 0xFFFF) && r != '\t' && r != '\n' && r != '\r' {
			b.WriteRune(' ')
			continue
		}
		if tz.handleChinese && isCJK(r) {
			b.WriteRune(' ')
			b.WriteRune(r)
			b.WriteRune(' ')
			continue
		}
		b.WriteRune(r)
	}
	out := b.String()
	if tz.lowercase {
		out = strings.ToLower(out)
	}
	if tz.stripAccents {
		out = norm.NFD.String(out)
		var stripped strings.Builder
		for _, r := range out {
			if !unicode.Is(unicode.Mn, r) {
				stripped.WriteRune(r)
			}
		}
		out = stripped.String()
	}
	return out
}

func (tz *Tokenizer) preTokenize(s string) []string {
	var words []string
	var cur strings.Builder
	flush := func() {
		if cur.Len() > 0 {
			words = append(words, cur.String())
			cur.Reset()
		}
	}
	for _, r := range s {
		switch {
		case unicode.IsSpace(r):
			flush()
		case isPunct(r):
			flush()
			words = append(words, string(r))
		default:
			cur.WriteRune(r)
		}
	}
	flush()
	return words
}

func (tz *Tokenizer) wordPiece(word string) []string {
	runes := []rune(word)
	if len(runes) > tz.maxWordChars {
		return []string{tz.unk}
	}
	var out []string
	start := 0
	bad := false
	for start < len(runes) {
		curEnd := len(runes)
		found := -1
		for start < curEnd {
			sub := string(runes[start:curEnd])
			if start > 0 {
				sub = tz.continuing + sub
			}
			if _, ok := tz.vocab[sub]; ok {
				found = curEnd
				out = append(out, sub)
				break
			}
			curEnd--
		}
		if found < 0 {
			bad = true
			break
		}
		start = found
	}
	if bad {
		return []string{tz.unk}
	}
	return out
}

func (tz *Tokenizer) Encode(text string) []string {
	var tokens []string
	for _, w := range tz.preTokenize(tz.normalize(text)) {
		tokens = append(tokens, tz.wordPiece(w)...)
	}
	return tokens
}

func (tz *Tokenizer) IDs(text string) []int {
	toks := append([]string{tz.cls}, tz.Encode(text)...)
	toks = append(toks, tz.sep)
	ids := make([]int, 0, len(toks))
	for _, t := range toks {
		if id, ok := tz.specials[t]; ok {
			ids = append(ids, id)
			continue
		}
		if id, ok := tz.vocab[t]; ok {
			ids = append(ids, id)
			continue
		}
		ids = append(ids, tz.specials[tz.unk])
	}
	return ids
}

type pyCase struct {
	Text      string  `json:"text"`
	InputIDs  []int   `json:"input_ids"`
	Tokens    []string `json:"tokens"`
}

func main() {
	tz, err := LoadTokenizer(os.Args[1])
	if err != nil {
		fmt.Println("load:", err)
		os.Exit(1)
	}
	raw, err := os.ReadFile(os.Args[2])
	if err != nil {
		fmt.Println("cases:", err)
		os.Exit(1)
	}
	var cases []pyCase
	if err := json.Unmarshal(raw, &cases); err != nil {
		fmt.Println("unmarshal:", err)
		os.Exit(1)
	}
	failed := 0
	for _, c := range cases {
		got := tz.IDs(c.Text)
		match := len(got) == len(c.InputIDs)
		if match {
			for i := range got {
				if got[i] != c.InputIDs[i] {
					match = false
					break
				}
			}
		}
		if !match {
			failed++
			fmt.Printf("MISMATCH len(go)=%d len(py)=%d text=%q\n  go=%v\n  py=%v\n  pytokens=%v\n", len(got), len(c.InputIDs), trunc(c.Text), got, c.InputIDs, c.Tokens)
		} else {
			fmt.Printf("OK   %2d tokens  %q\n", len(got), trunc(c.Text))
		}
	}
	fmt.Printf("\nTOKENIZER PARITY: %d/%d exact\n", len(cases)-failed, len(cases))
	if failed > 0 {
		os.Exit(2)
	}
}

func trunc(s string) string {
	if len(s) > 46 {
		return s[:43] + "..."
	}
	return s
}
