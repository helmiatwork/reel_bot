# frozen_string_literal: true

require "rails_helper"

RSpec.describe UrlSafetyValidator do
  describe ".validate!" do
    it "accepts valid public URLs" do
      expect {
        described_class.validate!("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
      }.not_to raise_error

      expect {
        described_class.validate!("https://youtu.be/dQw4w9WgXcQ")
      }.not_to raise_error
    end

    it "raises ArgumentError when URL is blank" do
      expect {
        described_class.validate!("")
      }.to raise_error(ArgumentError, "URL cannot be blank")

      expect {
        described_class.validate!(nil)
      }.to raise_error(ArgumentError, "URL cannot be blank")
    end

    it "raises ArgumentError when URL contains prohibited characters" do
      expect {
        described_class.validate!("https://youtube.com/watch?v=1; rm -rf /")
      }.to raise_error(ArgumentError, "URL contains invalid or prohibited characters")
    end

    it "raises ArgumentError for non-HTTP/HTTPS URLs" do
      expect {
        described_class.validate!("ftp://example.com/video.mp4")
      }.to raise_error(ArgumentError, "URL must use HTTP or HTTPS scheme and have a host")

      expect {
        described_class.validate!("file:///etc/passwd")
      }.to raise_error(ArgumentError, "URL must use HTTP or HTTPS scheme and have a host")
    end

    it "raises ArgumentError for URLs without a host" do
      expect {
        described_class.validate!("https://")
      }.to raise_error(ArgumentError, "URL must use HTTP or HTTPS scheme and have a host")
    end

    it "raises ArgumentError for invalid URI syntax" do
      allow(URI).to receive(:parse).and_raise(URI::InvalidURIError.new("bad"))
      expect {
        described_class.validate!("https://youtube.com/watch?v=123")
      }.to raise_error(ArgumentError, "URL is invalid")
    end

    describe "SSRF prevention" do
      it "rejects localhost and local domains" do
        %w[
          http://localhost
          http://localhost:3000/test
          http://foo.localhost
          http://app.local
          http://db.internal
          http://router.lan
        ].each do |url|
          expect {
            described_class.validate!(url)
          }.to raise_error(ArgumentError, "URL cannot target private or restricted network addresses")
        end
      end

      it "rejects private and loopback IPv4 addresses" do
        %w[
          http://127.0.0.1
          http://127.0.0.2:8080
          http://10.0.0.1
          http://10.255.255.254
          http://172.16.0.1
          http://172.31.255.254
          http://192.168.0.1
          http://192.168.1.100
        ].each do |url|
          expect {
            described_class.validate!(url)
          }.to raise_error(ArgumentError, "URL cannot target private or restricted network addresses")
        end
      end

      it "rejects link-local, unspecified, and reserved IP ranges" do
        %w[
          http://0.0.0.0
          http://169.254.169.254
          http://169.254.1.1
          http://100.64.0.1
          http://192.0.0.1
          http://198.18.0.1
          http://240.0.0.1
        ].each do |url|
          expect {
            described_class.validate!(url)
          }.to raise_error(ArgumentError, "URL cannot target private or restricted network addresses")
        end
      end

      it "rejects IPv6 loopback, unspecified, and private addresses" do
        %w[
          http://[::1]
          http://[::]
          http://[fc00::1]
          http://[fe80::1]
        ].each do |url|
          expect {
            described_class.validate!(url)
          }.to raise_error(ArgumentError, "URL cannot target private or restricted network addresses")
        end
      end

      it "rejects integer and hex representation of loopback addresses" do
        # 2130706433 is decimal for 127.0.0.1
        expect {
          described_class.validate!("http://2130706433/test")
        }.to raise_error(ArgumentError, "URL cannot target private or restricted network addresses")

        # 0x7f000001 is hex for 127.0.0.1
        expect {
          described_class.validate!("http://0x7f000001/test")
        }.to raise_error(ArgumentError, "URL cannot target private or restricted network addresses")
      end

      it "rejects domain names that resolve to private IP addresses via DNS" do
        allow(Resolv).to receive(:getaddresses).with("malicious.test").and_return([ "127.0.0.1" ])

        expect {
          described_class.validate!("http://malicious.test/video")
        }.to raise_error(ArgumentError, "URL cannot target private or restricted network addresses")
      end
    end

    describe "trusted_only option" do
      it "accepts valid HTTPS YouTube URLs when trusted_only is true" do
        expect {
          described_class.validate!("https://www.youtube.com/watch?v=dQw4w9WgXcQ", trusted_only: true)
        }.not_to raise_error

        expect {
          described_class.validate!("https://youtu.be/dQw4w9WgXcQ", trusted_only: true)
        }.not_to raise_error
      end

      it "rejects non-trusted domains when trusted_only is true" do
        %w[
          https://example.com/video.mp4
          https://attacker.com/exploit
          https://vimeo.com/12345
          https://notyoutube.com/watch
        ].each do |url|
          expect {
            described_class.validate!(url, trusted_only: true)
          }.to raise_error(ArgumentError, "URL must belong to trusted domain (youtube.com, youtu.be)")
        end
      end

      it "rejects non-HTTPS scheme when trusted_only is true" do
        expect {
          described_class.validate!("http://www.youtube.com/watch?v=dQw4w9WgXcQ", trusted_only: true)
        }.to raise_error(ArgumentError, "URL must use HTTPS scheme")
      end

      it "allows arbitrary public URLs when trusted_only is false" do
        expect {
          described_class.validate!("https://example.com/video.mp4", trusted_only: false)
        }.not_to raise_error
      end
    end
  end

  describe ".validate_youtube_url!" do
    it "validates HTTPS YouTube URLs and rejects non-trusted domains" do
      expect {
        described_class.validate_youtube_url!("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
      }.not_to raise_error

      expect {
        described_class.validate_youtube_url!("https://attacker.com")
      }.to raise_error(ArgumentError, "URL must belong to trusted domain (youtube.com, youtu.be)")
    end

    it "rejects HTTP YouTube URLs" do
      expect {
        described_class.validate_youtube_url!("http://www.youtube.com/watch?v=dQw4w9WgXcQ")
      }.to raise_error(ArgumentError, "URL must use HTTPS scheme")
    end
  end
end
