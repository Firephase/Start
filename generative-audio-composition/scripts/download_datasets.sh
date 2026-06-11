#!/usr/bin/env bash
# =============================================================================
# download_datasets.sh
#
# Downloads and prepares all training datasets for the generative audio
# composition system.
#
# Datasets:
#   - OpenSinger   (multi-singer Mandarin/English singing corpus)
#   - VocalSet     (16-singer technique dataset)
#   - FMA Large    (Free Music Archive, 106 GB, 30-second clips)
#   - MUSDB18-HQ   (150 stereo tracks, instrument-separated stems)
#   - VoxCeleb2    (speaker identity, 2,442 speakers)
#
# Usage:
#   DATA_DIR=/data/audio ./scripts/download_datasets.sh
#   DATA_DIR=/data/audio ./scripts/download_datasets.sh --dataset fma
# =============================================================================

set -euo pipefail

# ── Defaults ──────────────────────────────────────────────────────────────────
DATA_DIR="${DATA_DIR:-/data/audio}"
DOWNLOAD_ONLY="${DOWNLOAD_ONLY:-false}"  # set true to skip extraction
VERIFY_CHECKSUMS="${VERIFY_CHECKSUMS:-true}"
PARALLEL_DOWNLOADS="${PARALLEL_DOWNLOADS:-4}"

# ── Colours ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Colour

info()    { echo -e "${BLUE}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }
die()     { error "$*"; exit 1; }

# ── Helpers ───────────────────────────────────────────────────────────────────

require_cmd() {
    command -v "$1" >/dev/null 2>&1 || die "'$1' is required but not installed. Please install it and try again."
}

human_size() {
    # Print human-readable size of a path
    local path="$1"
    if [ -d "$path" ]; then
        du -sh "$path" 2>/dev/null | cut -f1
    elif [ -f "$path" ]; then
        ls -lh "$path" | awk '{print $5}'
    else
        echo "N/A"
    fi
}

verify_md5() {
    local file="$1"
    local expected_md5="$2"
    if [ "$VERIFY_CHECKSUMS" != "true" ]; then
        warn "Checksum verification skipped (VERIFY_CHECKSUMS=false)"
        return 0
    fi
    info "Verifying MD5 for $(basename "$file") …"
    local actual_md5
    actual_md5=$(md5sum "$file" | awk '{print $1}')
    if [ "$actual_md5" != "$expected_md5" ]; then
        die "MD5 mismatch for $file\n  expected: $expected_md5\n  got:      $actual_md5"
    fi
    success "MD5 OK: $expected_md5"
}

download_file() {
    local url="$1"
    local dest="$2"
    local desc="${3:-$(basename "$dest")}"

    if [ -f "$dest" ]; then
        info "Already downloaded: $desc — skipping"
        return 0
    fi

    info "Downloading $desc …"
    mkdir -p "$(dirname "$dest")"

    if command -v wget >/dev/null 2>&1; then
        wget --progress=bar:force:noscroll \
             --continue \
             --tries=3 \
             --timeout=60 \
             -O "$dest" \
             "$url" || { rm -f "$dest"; die "wget failed for $url"; }
    else
        curl --location \
             --retry 3 \
             --retry-delay 5 \
             --progress-bar \
             --output "$dest" \
             "$url" || { rm -f "$dest"; die "curl failed for $url"; }
    fi
    success "Downloaded: $desc ($(human_size "$dest"))"
}

extract_archive() {
    local archive="$1"
    local dest_dir="$2"

    if [ "$DOWNLOAD_ONLY" = "true" ]; then
        warn "DOWNLOAD_ONLY=true — skipping extraction of $(basename "$archive")"
        return 0
    fi

    info "Extracting $(basename "$archive") → $dest_dir …"
    mkdir -p "$dest_dir"

    case "$archive" in
        *.tar.gz|*.tgz) tar -xzf "$archive" -C "$dest_dir" ;;
        *.tar.bz2)       tar -xjf "$archive" -C "$dest_dir" ;;
        *.tar.xz)        tar -xJf "$archive" -C "$dest_dir" ;;
        *.zip)           unzip -q "$archive" -d "$dest_dir" ;;
        *.gz)            gunzip -k "$archive" ;;
        *) die "Unknown archive type: $archive" ;;
    esac
    success "Extracted to $dest_dir ($(human_size "$dest_dir"))"
}

# ── Prerequisite checks ───────────────────────────────────────────────────────

require_cmd md5sum
require_cmd tar

# ── Argument parsing ──────────────────────────────────────────────────────────

DATASETS_TO_DOWNLOAD=("opensinger" "vocalset" "fma" "musdb18hq" "voxceleb2")

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dataset)
            DATASETS_TO_DOWNLOAD=("$2")
            shift 2
            ;;
        --data-dir)
            DATA_DIR="$2"
            shift 2
            ;;
        --no-verify)
            VERIFY_CHECKSUMS=false
            shift
            ;;
        --download-only)
            DOWNLOAD_ONLY=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [--dataset <name>] [--data-dir <path>] [--no-verify] [--download-only]"
            echo ""
            echo "Available datasets: opensinger vocalset fma musdb18hq voxceleb2"
            exit 0
            ;;
        *)
            die "Unknown argument: $1"
            ;;
    esac
done

# ── Create base directory ─────────────────────────────────────────────────────

mkdir -p "$DATA_DIR"
info "Data directory: $DATA_DIR"

# =============================================================================
# Dataset download functions
# =============================================================================

# ── OpenSinger ────────────────────────────────────────────────────────────────
download_opensinger() {
    local name="OpenSinger"
    local dir="$DATA_DIR/opensinger"

    info "=== $name ==="
    if [ -d "$dir/wavs" ]; then
        success "$name already prepared at $dir — skipping"
        return 0
    fi

    # OpenSinger is hosted on Zenodo (DOI: 10.5281/zenodo.4922619)
    local base_url="https://zenodo.org/record/4922619/files"
    local archive="$dir/OpenSinger.tar.gz"
    # NOTE: Checksums below are illustrative; replace with official values.
    local md5="a8b3d2e4f1c097650f3842b1e9d27c5a"

    mkdir -p "$dir"
    download_file "${base_url}/OpenSinger.tar.gz" "$archive" "$name archive"
    verify_md5 "$archive" "$md5"
    extract_archive "$archive" "$dir"

    # Organise: move singer directories to $dir/wavs/
    mkdir -p "$dir/wavs"
    find "$dir" -name "*.wav" -not -path "*/wavs/*" -exec mv {} "$dir/wavs/" \; 2>/dev/null || true

    success "$name ready — $(human_size "$dir")"
}

# ── VocalSet ──────────────────────────────────────────────────────────────────
download_vocalset() {
    local name="VocalSet"
    local dir="$DATA_DIR/vocalset"

    info "=== $name ==="
    if [ -d "$dir/data_by_singer" ]; then
        success "$name already prepared at $dir — skipping"
        return 0
    fi

    # VocalSet: https://zenodo.org/record/1442513
    local url="https://zenodo.org/record/1442513/files/VocalSet11.tar.gz"
    local archive="$dir/VocalSet11.tar.gz"
    local md5="c3a7d9e2f8b541630c95d7a4b2e81f06"

    mkdir -p "$dir"
    download_file "$url" "$archive" "$name archive"
    verify_md5 "$archive" "$md5"
    extract_archive "$archive" "$dir"

    success "$name ready — $(human_size "$dir")"
}

# ── FMA Large ─────────────────────────────────────────────────────────────────
download_fma() {
    local name="FMA Large"
    local dir="$DATA_DIR/fma"

    info "=== $name ==="
    if [ -d "$dir/fma_large" ]; then
        success "$name already prepared at $dir — skipping"
        return 0
    fi

    warn "$name is ~106 GB. This may take a long time."

    # FMA: https://github.com/mdeff/fma
    local base_url="https://os.unil.cloud.switch.ch/fma"
    local archive_audio="$dir/fma_large.zip"
    local archive_meta="$dir/fma_metadata.zip"
    local md5_audio="497109f4dd721066b561f079f9a00a23"
    local md5_meta="f0df49ffe5f2a6008d7dc83c6915b31d"

    mkdir -p "$dir"
    download_file "${base_url}/fma_large.zip"    "$archive_audio" "$name audio"
    download_file "${base_url}/fma_metadata.zip" "$archive_meta"  "$name metadata"
    verify_md5 "$archive_audio" "$md5_audio"
    verify_md5 "$archive_meta"  "$md5_meta"
    extract_archive "$archive_audio" "$dir"
    extract_archive "$archive_meta"  "$dir"

    success "$name ready — $(human_size "$dir")"
}

# ── MUSDB18-HQ ────────────────────────────────────────────────────────────────
download_musdb18hq() {
    local name="MUSDB18-HQ"
    local dir="$DATA_DIR/musdb18hq"

    info "=== $name ==="
    if [ -d "$dir/train" ] && [ -d "$dir/test" ]; then
        success "$name already prepared at $dir — skipping"
        return 0
    fi

    warn "$name is ~30 GB."

    # MUSDB18-HQ: https://zenodo.org/record/3338373
    local url="https://zenodo.org/record/3338373/files/musdb18hq.zip"
    local archive="$dir/musdb18hq.zip"
    local md5="baee34e5eddee53e6bdca50e6c48c17c"

    mkdir -p "$dir"
    download_file "$url" "$archive" "$name archive"
    verify_md5 "$archive" "$md5"
    extract_archive "$archive" "$dir"

    # Verify expected structure
    if [ ! -d "$dir/train" ]; then
        warn "Expected $dir/train not found after extraction — check archive layout"
    fi

    success "$name ready — $(human_size "$dir")"
}

# ── VoxCeleb2 ────────────────────────────────────────────────────────────────
download_voxceleb2() {
    local name="VoxCeleb2"
    local dir="$DATA_DIR/voxceleb2"

    info "=== $name ==="
    if [ -d "$dir/dev/aac" ] || [ -d "$dir/dev/wav" ]; then
        success "$name already prepared at $dir — skipping"
        return 0
    fi

    warn "$name (~65 GB) requires registration at https://www.robots.ox.ac.uk/~vgg/data/voxceleb/"
    warn "Set VOXCELEB2_URL to your download URL (includes authentication token)."

    local url="${VOXCELEB2_URL:-}"
    if [ -z "$url" ]; then
        warn "VOXCELEB2_URL not set — skipping $name download."
        warn "Register at https://www.robots.ox.ac.uk/~vgg/data/voxceleb/vox2.html"
        warn "Then re-run with:  VOXCELEB2_URL=<url> $0 --dataset voxceleb2"
        return 0
    fi

    local archive_dev="$dir/vox2_aac_dev.zip"
    local archive_test="$dir/vox2_aac_test.zip"
    local md5_dev="b4d44d6a57e73fbd0a4e05b8d7ec2afc"
    local md5_test="09a98f48c0148bf1a7e0dafd06ee7073"

    mkdir -p "$dir"
    download_file "${url}/vox2_aac_dev.zip"  "$archive_dev"  "$name dev set"
    download_file "${url}/vox2_aac_test.zip" "$archive_test" "$name test set"
    verify_md5 "$archive_dev"  "$md5_dev"
    verify_md5 "$archive_test" "$md5_test"
    extract_archive "$archive_dev"  "$dir/dev"
    extract_archive "$archive_test" "$dir/test"

    # Convert AAC to WAV for compatibility
    if command -v ffmpeg >/dev/null 2>&1; then
        info "Converting AAC to WAV (this takes a while) …"
        find "$dir" -name "*.m4a" | while read -r f; do
            wav="${f%.m4a}.wav"
            ffmpeg -i "$f" -ar 16000 -ac 1 "$wav" -y -loglevel error && rm "$f"
        done
        success "AAC → WAV conversion complete"
    else
        warn "ffmpeg not found — leaving files in AAC format"
    fi

    success "$name ready — $(human_size "$dir")"
}

# =============================================================================
# Main
# =============================================================================

echo ""
info "Starting dataset downloads"
info "Target directory : $DATA_DIR"
info "Datasets         : ${DATASETS_TO_DOWNLOAD[*]}"
info "Verify checksums : $VERIFY_CHECKSUMS"
echo ""

for dataset in "${DATASETS_TO_DOWNLOAD[@]}"; do
    case "$dataset" in
        opensinger)  download_opensinger  ;;
        vocalset)    download_vocalset    ;;
        fma)         download_fma         ;;
        musdb18hq)   download_musdb18hq   ;;
        voxceleb2)   download_voxceleb2   ;;
        *)           warn "Unknown dataset '$dataset' — skipping" ;;
    esac
    echo ""
done

echo ""
success "All requested datasets processed."
info "Total data directory size: $(human_size "$DATA_DIR")"
