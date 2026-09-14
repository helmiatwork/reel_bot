require 'rails_helper'

RSpec.describe SubtitleService do
  let(:service) { described_class.new }
  let(:video_path) { Rails.root.join('tmp', 'input_video.mp4').to_s }
  let(:srt_path) { Rails.root.join('tmp', 'captions.srt').to_s }
  let(:output_path) { Rails.root.join('tmp', 'subtitled_video.mp4').to_s }

  before do
    FileUtils.touch(video_path)
    FileUtils.touch(srt_path)
  end

  after do
    FileUtils.rm_f(video_path)
    FileUtils.rm_f(srt_path)
    FileUtils.rm_f(output_path)
  end

  describe "DEFAULT_STYLE" do
    it "defines and freezes DEFAULT_STYLE" do
      expect(described_class::DEFAULT_STYLE).to eq(
        "Bold=1,FontSize=16,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=2,BorderStyle=1,Alignment=2,MarginV=20"
      )
      expect(described_class::DEFAULT_STYLE).to be_frozen
    end
  end

  describe '#generate_srt' do
    it 'creates a valid SRT file given script or dialogue segments' do
      segments = [
        { start_time: 0.0, end_time: 3.5, text: 'Welcome to this awesome tutorial.' },
        { start_time: 3.5, end_time: 7.25, text: 'Here are three tools you must know.' }
      ]

      result = service.generate_srt(video_path, srt_path, segments: segments)
      expect(result).to eq(srt_path)
      expect(File.exist?(srt_path)).to be true

      content = File.read(srt_path)
      expect(content).to include("1\n00:00:00,000 --> 00:00:03,500\nWelcome to this awesome tutorial.")
      expect(content).to include("2\n00:00:03,500 --> 00:00:07,250\nHere are three tools you must know.")
    end

    it 'creates an empty SRT file if no segments are detected' do
      result = service.generate_srt(video_path, srt_path, segments: [])
      expect(result).to eq(srt_path)
      expect(File.read(srt_path).strip).to be_empty
    end
  end

  describe '#burn_subtitles' do
    it 'executes ffmpeg with escaped subtitles filter arguments' do
      status = instance_double(Process::Status, success?: true)

      expect(Open3).to receive(:capture3) do |*args|
        expect(args[0]).to eq('ffmpeg')
        expect(args).to include('-i', video_path)
        expect(args).to include('-c:v', 'libx264', '-crf', '23', '-c:a', 'copy')
        filter_idx = args.index('-vf')
        expect(filter_idx).not_to be_nil
        filter_arg = args[filter_idx + 1]
        expect(filter_arg).to match(/^subtitles=/)
        FileUtils.touch(output_path)
        [ '', '', status ]
      end

      result = service.burn_subtitles(video_path, srt_path, output_path)
      expect(result).to eq(output_path)
    end

    it "allows a valid custom style parameter" do
      custom_style = "FontSize=20,PrimaryColour=&H0000FFFF"
      status = instance_double(Process::Status, success?: true)
      expect(Open3).to receive(:capture3) do |*args|
        filter_arg = args[args.index("-vf") + 1]
        expect(filter_arg).to include("force_style='#{custom_style}'")
        FileUtils.touch(output_path)
        [ "", "", status ]
      end

      result = service.burn_subtitles(video_path, srt_path, output_path, style: custom_style)
      expect(result).to eq(output_path)
    end

    it "raises ArgumentError when style contains quotes, colons, semicolons, or invalid chars" do
      malicious_styles = [
        "Bold=1;rm -rf /",
        "FontSize=16,fontname='Arial'",
        'FontSize=16,fontname="Arial"',
        "FontSize=16:MarginV=20",
        "FontSize=16\nAlignment=2",
        "FontSize=16`whoami`",
        "FontSize=16|cat /etc/passwd",
        "Bold=1 FontSize=16"
      ]

      malicious_styles.each do |bad_style|
        expect {
          service.burn_subtitles(video_path, srt_path, output_path, style: bad_style)
        }.to raise_error(ArgumentError, "Invalid subtitle style parameters")
      end
    end

    it 'escapes colons and single quotes in the srt path' do
      tricky_srt = Rails.root.join('tmp', "test:it's.srt").to_s
      FileUtils.touch(tricky_srt)

      status = instance_double(Process::Status, success?: true)
      expect(Open3).to receive(:capture3) do |*args|
        filter_arg = args[args.index('-vf') + 1]
        expect(filter_arg).to include('\:')
        expect(filter_arg).to include("\\'")
        FileUtils.touch(output_path)
        [ '', '', status ]
      end

      service.burn_subtitles(video_path, tricky_srt, output_path)
      FileUtils.rm_f(tricky_srt)
    end

    it 'cleans up output file and raises SubtitleService::Error when ffmpeg fails' do
      FileUtils.touch(output_path)
      status = instance_double(Process::Status, success?: false, exitstatus: 1)
      allow(Open3).to receive(:capture3).and_return([ '', 'libass error: subtitles invalid', status ])

      expect {
        service.burn_subtitles(video_path, srt_path, output_path)
      }.to raise_error(SubtitleService::Error, /burning failed/)

      expect(File.exist?(output_path)).to be false
    end
  end
end
