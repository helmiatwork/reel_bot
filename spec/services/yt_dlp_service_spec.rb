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
  end
end
