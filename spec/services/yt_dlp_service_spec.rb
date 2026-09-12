# frozen_string_literal: true

require "rails_helper"
require "open3"

RSpec.describe YtDlpService do
  subject(:service) { described_class.new }

  let(:valid_url) { "https://www.youtube.com/watch?v=dQw4w9WgXcQ" }

  describe "URL validation and injection prevention" do
    prohibited_urls = [
      "https://www.youtube.com/watch?v=123; rm -rf /",
      "https://www.youtube.com/watch?v=123 && echo hacked",
      "https://www.youtube.com/watch?v=123 | cat /etc/passwd",
      "https://www.youtube.com/watch?v=123`id`",
      "https://www.youtube.com/watch?v=123$(whoami)",
      "https://www.youtube.com/watch?v=123\nmalicious",
      "https://www.youtube.com/watch?v=123\rmalicious",
      "https://www.youtube.com/watch?v=123<script>",
      "https://www.youtube.com/watch?v=123>out"
    ]

    prohibited_urls.each do |bad_url|
      it "raises ArgumentError for command injection attempt: #{bad_url.inspect}" do
        expect { service.fetch_metadata(bad_url) }.to raise_error(ArgumentError, /invalid or prohibited/)
        expect { service.fetch_transcript(bad_url) }.to raise_error(ArgumentError, /invalid or prohibited/)
        expect { service.download(bad_url, output_dir: "/tmp") }.to raise_error(ArgumentError, /invalid or prohibited/)
      end
    end

    it "raises ArgumentError when URL is blank" do
      expect { service.fetch_metadata("") }.to raise_error(ArgumentError, /URL cannot be blank/)
    end

    it "raises ArgumentError for non-HTTP/HTTPS URLs" do
      expect { service.fetch_metadata("file:///etc/passwd") }.to raise_error(ArgumentError, /HTTP or HTTPS/)
      expect { service.fetch_metadata("ftp://example.com/video.mp4") }.to raise_error(ArgumentError, /HTTP or HTTPS/)
    end

    it "raises ArgumentError on invalid URI syntax" do
      allow(URI).to receive(:parse).and_raise(URI::InvalidURIError.new("bad"))
      expect { service.fetch_metadata(valid_url) }.to raise_error(ArgumentError, /URL is invalid/)
    end

    describe "SSRF and restricted host prevention" do
      ssrf_urls = [
        "http://localhost/video.mp4",
        "https://localhost:8080/video.mp4",
        "http://127.0.0.1/video.mp4",
        "http://127.0.0.2:3000/video.mp4",
        "http://0.0.0.0/video.mp4",
        "http://169.254.169.254/latest/meta-data",
        "http://10.0.0.1/video.mp4",
        "http://172.16.0.1/video.mp4",
        "http://192.168.1.1/video.mp4",
        "http://[::1]/video.mp4",
        "http://[::]/video.mp4",
        "http://foo.localhost/video.mp4"
      ]

      ssrf_urls.each do |bad_url|
        it "raises ArgumentError for SSRF attempt: #{bad_url}" do
          expect { service.fetch_metadata(bad_url) }.to raise_error(ArgumentError, /private or restricted/)
          expect { service.fetch_transcript(bad_url) }.to raise_error(ArgumentError, /private or restricted/)
          expect { service.download(bad_url, output_dir: "/tmp") }.to raise_error(ArgumentError, /private or restricted/)
        end
      end
    end
  end

  describe "execution safety with Open3.capture3" do
    it "executes commands as an array of arguments, never a shell string" do
      status = instance_double(Process::Status, success?: true)
      allow(Open3).to receive(:capture3).and_return([ '{"title": "Test Video"}', "", status ])

      service.fetch_metadata(valid_url)

      expect(Open3).to have_received(:capture3) do |*args|
        expect(args).to be_an(Array)
        expect(args.first).to eq("yt-dlp")
        expect(args).to include("--dump-json")
        expect(args).to include(valid_url)
      end
    end
  end

  describe "error handling" do
    it "raises YtDlpService::BinaryNotFoundError when yt-dlp binary is missing" do
      allow(Open3).to receive(:capture3).and_raise(Errno::ENOENT.new("No such file or directory - yt-dlp"))

      expect { service.fetch_metadata(valid_url) }.to raise_error(YtDlpService::BinaryNotFoundError, /binary not found/)
    end

    it "raises YtDlpService::TimeoutError when execution exceeds timeout" do
      allow(Timeout).to receive(:timeout).and_raise(Timeout::Error.new("execution expired"))

      expect { service.fetch_metadata(valid_url) }.to raise_error(YtDlpService::TimeoutError, /timed out/)
    end

    it "raises YtDlpService::ExecutionError when yt-dlp exits with non-zero status" do
      status = instance_double(Process::Status, success?: false, exitstatus: 1)
      allow(Open3).to receive(:capture3).and_return([ "", "ERROR: Video unavailable", status ])

      expect { service.fetch_metadata(valid_url) }.to raise_error(YtDlpService::ExecutionError, /Video unavailable/)
    end
  end

  describe "#fetch_metadata" do
    it "returns parsed JSON hash from yt-dlp output" do
      json_output = { "id" => "dQw4w9WgXcQ", "title" => "Never Gonna Give You Up", "duration" => 212 }.to_json
      status = instance_double(Process::Status, success?: true)
      allow(Open3).to receive(:capture3).and_return([ json_output, "", status ])

      result = service.fetch_metadata(valid_url)
      expect(result).to eq({ "id" => "dQw4w9WgXcQ", "title" => "Never Gonna Give You Up", "duration" => 212 })
    end
  end

  describe "#fetch_transcript" do
    let(:sample_vtt) do
      <<~VTT
        WEBVTT
        Kind: captions
        Language: en

        01:10:05.500 --> 01:10:20.000
        First segment with hours

        20.0 --> 35.5
        Raw float format
      VTT
    end

    it "extracts subtitles and returns segments with start, end, and text" do
      status = instance_double(Process::Status, success?: true)
      allow(Open3).to receive(:capture3) do |*args|
        o_idx = args.index("-o")
        output_base = args[o_idx + 1]
        File.write("#{output_base}.en.vtt", sample_vtt)
        [ "", "", status ]
      end

      result = service.fetch_transcript(valid_url)
      expect(result).to be_a(Hash)
      expect(result[:segments]).to be_an(Array)
      expect(result[:segments].size).to eq(2)
      expect(result[:segments][0][:start]).to eq(4205.5)
      expect(result[:segments][0][:text]).to eq("First segment with hours")
      expect(result[:segments][1][:start]).to eq(20.0)
    end


    it "returns { segments: [] } gracefully when subtitles are not available or command fails" do
      status = instance_double(Process::Status, success?: false, exitstatus: 1)
      allow(Open3).to receive(:capture3).and_return([ "", "WARNING: video has no subtitles", status ])

      result = service.fetch_transcript(valid_url)
      expect(result).to eq({ segments: [] })
    end
  end

  describe "#download" do
    let(:output_dir) { Dir.mktmpdir("yt_dlp_test") }

    after do
      FileUtils.remove_entry(output_dir) if Dir.exist?(output_dir)
    end

    it "downloads video into output_dir and returns the file path" do
      status = instance_double(Process::Status, success?: true)
      target_file = File.join(output_dir, "dQw4w9WgXcQ.mp4")

      allow(Open3).to receive(:capture3) do |*args|
        File.write(target_file, "fake-video-content")
        [ target_file, "", status ]
      end

      result = service.download(valid_url, output_dir: output_dir)
      expect(result).to eq(target_file)
      expect(File.exist?(result)).to be(true)
    end

    it "passes --print after_move:filepath to yt-dlp arguments" do
      status = instance_double(Process::Status, success?: true)
      target_file = File.join(output_dir, "dQw4w9WgXcQ.mp4")

      allow(Open3).to receive(:capture3) do |*args|
        expect(args).to include("--print", "after_move:filepath")
        File.write(target_file, "fake-video-content")
        [ target_file, "", status ]
      end

      service.download(valid_url, output_dir: output_dir)
    end

    it "isolates downloads into a unique uuid subdirectory under data/videos when output_dir is default" do
      status = instance_double(Process::Status, success?: true)

      allow(Open3).to receive(:capture3) do |*args|
        o_idx = args.index("-o")
        template = args[o_idx + 1]
        dest_dir = File.dirname(template)
        target_file = File.join(dest_dir, "dQw4w9WgXcQ.mp4")
        File.write(target_file, "fake-video-content")
        [ "#{target_file}\n", "", status ]
      end

      result = service.download(valid_url)
      expect(File.exist?(result)).to be(true)
      expect(result).to match(%r{data/videos/[a-f0-9-]+/dQw4w9WgXcQ\.mp4})
      FileUtils.rm_rf(File.dirname(result))
    end

    it "resolves the downloaded file using yt-dlp stdout rather than picking newest from shared dir" do
      shared_dir = output_dir
      older_file = File.join(shared_dir, "older.mp4")
      target_file = File.join(shared_dir, "correct_target.mp4")
      competing_newer_file = File.join(shared_dir, "competing_newer.mp4")

      File.write(older_file, "older")
      File.write(target_file, "target")
      sleep 0.05
      File.write(competing_newer_file, "newer")

      status = instance_double(Process::Status, success?: true)
      allow(Open3).to receive(:capture3).and_return([ "\n#{target_file}\n", "", status ])

      result = service.download(valid_url, output_dir: shared_dir)
      expect(result).to eq(target_file)
    end

    it "falls back to verified file in destination directory when stdout path is missing" do
      status = instance_double(Process::Status, success?: true)
      target_file = File.join(output_dir, "fallback.mp4")

      allow(Open3).to receive(:capture3) do |*args|
        File.write(target_file, "fallback-content")
        [ "", "", status ]
      end

      result = service.download(valid_url, output_dir: output_dir)
      expect(result).to eq(target_file)
    end

    it "raises ExecutionError when yt-dlp completes but no output file exists" do
      status = instance_double(Process::Status, success?: true)
      allow(Open3).to receive(:capture3).and_return([ "nonexistent_file.mp4\n", "", status ])

      expect {
        service.download(valid_url, output_dir: output_dir)
      }.to raise_error(YtDlpService::ExecutionError, /output file not found/)
    end
  end

  describe "#latest_channel_video" do
    it "fetches the latest channel video by calling yt-dlp flat playlist" do
      status = instance_double(Process::Status, success?: true)
      json_line = { "id" => "vid_dlp_1", "title" => "Great Tech Review" }.to_json
      allow(Open3).to receive(:capture3).and_return([ "#{json_line}\n", "", status ])

      result = service.latest_channel_video("@techreview")
      expect(result).to eq({
        video_id: "vid_dlp_1",
        title: "Great Tech Review"
      })

      expect(Open3).to have_received(:capture3) do |*args|
        expect(args).to include("https://www.youtube.com/@techreview/videos")
        expect(args).to include("--flat-playlist")
        expect(args).to include("--playlist-end", "1")
      end
    end

    it "handles UC channel IDs properly" do
      status = instance_double(Process::Status, success?: true)
      json_line = { "id" => "vid_dlp_2", "title" => "Channel Video" }.to_json
      allow(Open3).to receive(:capture3).and_return([ "#{json_line}\n", "", status ])

      result = service.latest_channel_video("UC123456789")
      expect(result[:video_id]).to eq("vid_dlp_2")

      expect(Open3).to have_received(:capture3) do |*args|
        expect(args).to include("https://www.youtube.com/channel/UC123456789/videos")
      end
    end

    it "returns nil when stdout is blank or has no video" do
      status = instance_double(Process::Status, success?: true)
      allow(Open3).to receive(:capture3).and_return([ "", "", status ])

      expect(service.latest_channel_video("@emptychan")).to be_nil
    end

    it "returns nil and rescues errors when yt-dlp fails" do
      allow(Open3).to receive(:capture3).and_raise(Errno::ENOENT.new("yt-dlp binary missing"))

      expect(service.latest_channel_video("@errorchan")).to be_nil
    end
  end
end
