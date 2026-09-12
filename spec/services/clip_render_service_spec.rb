# frozen_string_literal: true

require "rails_helper"
require "open3"

RSpec.describe ClipRenderService do
  let(:tmp_dir) { Dir.mktmpdir("render_spec") }
  let(:fake_source) { File.join(tmp_dir, "source.mp4") }
  let(:clip) do
    {
      "start_sec" => 10,
      "end_sec" => 25,
      "title" => "Viral Hook",
      "recommended" => true
    }
  end

  before do
    File.write(fake_source, "dummy-video-content")
  end

  after do
    FileUtils.remove_entry(tmp_dir) if Dir.exist?(tmp_dir)
  end

  describe "validation & security" do
    it "raises ArgumentError when input file does not exist" do
      expect {
        described_class.new(input_path: "/nonexistent/video.mp4", clip: clip).call
      }.to raise_error(ArgumentError, /Input file does not exist/)
    end

    it "raises ArgumentError on path traversal attempt in input_path" do
      expect {
        described_class.new(input_path: "#{tmp_dir}/../../../etc/passwd", clip: clip).call
      }.to raise_error(ArgumentError, /Path traversal/)
    end

    it "raises ArgumentError when clip is missing start_sec or end_sec" do
      expect {
        described_class.new(input_path: fake_source, clip: { "title" => "Bad clip" }).call
      }.to raise_error(ArgumentError, /start_sec and end_sec are required/)
    end

    it "raises ArgumentError when start_sec >= end_sec" do
      expect {
        described_class.new(input_path: fake_source, clip: { "start_sec" => 30, "end_sec" => 20 }).call
      }.to raise_error(ArgumentError, /start_sec must be less than end_sec/)
    end
  end

  describe "ffmpeg execution" do
    it "calls ffmpeg with array arguments via Open3.capture3" do
      status = instance_double(Process::Status, success?: true)

      allow(Open3).to receive(:capture3) do |*cmd|
        output_file = cmd.last
        FileUtils.mkdir_p(File.dirname(output_file))
        File.write(output_file, "dummy-output")
        [ "", "", status ]
      end

      service = described_class.new(input_path: fake_source, clip: clip)
      result = service.call

      expect(result[:status]).to eq("ok")
      expect(result[:video_path]).to be_present
      expect(result[:render_id]).to be_present
      expect(result[:clip]).to eq(clip)

      expect(Open3).to have_received(:capture3) do |*args|
        expect(args[0]).to eq("ffmpeg")
        expect(args).to include("-y")
        expect(args).to include("-ss")
        expect(args).to include("10")
        expect(args).to include("-to")
        expect(args).to include("25")
        expect(args).to include("-i")
        expect(args).to include(fake_source)
        expect(args).to include("-c")
        expect(args).to include("copy")
      end
    end

    it "raises ExecutionError when ffmpeg succeeds but output file is not created" do
      status = instance_double(Process::Status, success?: true)
      allow(Open3).to receive(:capture3).and_return([ "", "", status ])

      expect {
        described_class.new(input_path: fake_source, clip: clip).call
      }.to raise_error(ClipRenderService::ExecutionError, /Output file was not created/)
    end

    it "raises BinaryNotFoundError when ffmpeg is missing" do
      allow(Open3).to receive(:capture3).and_raise(Errno::ENOENT.new("No such file or directory - ffmpeg"))

      expect {
        described_class.new(input_path: fake_source, clip: clip).call
      }.to raise_error(ClipRenderService::BinaryNotFoundError, /ffmpeg binary not found/)
    end

    it "raises TimeoutError when ffmpeg times out" do
      allow(Timeout).to receive(:timeout).and_raise(Timeout::Error.new("execution expired"))

      expect {
        described_class.new(input_path: fake_source, clip: clip).call
      }.to raise_error(ClipRenderService::TimeoutError, /timed out/)
    end

    it "raises ExecutionError when ffmpeg exits with non-zero status" do
      status = instance_double(Process::Status, success?: false, exitstatus: 1)
      allow(Open3).to receive(:capture3).and_return([ "", "ffmpeg error: invalid codec", status ])

      expect {
        described_class.new(input_path: fake_source, clip: clip).call
      }.to raise_error(ClipRenderService::ExecutionError, /ffmpeg error/)
    end
  end
end
