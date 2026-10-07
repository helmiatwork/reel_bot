module Publishers
  class MultiPublisher
    SUPPORTED_PLATFORMS = %w[youtube tiktok instagram].freeze

    def publish_all(video_path:, script:, platforms:, credentials: {}, public_url: nil)
      return {} if platforms.blank?

      script_data = script.is_a?(Hash) ? script.with_indifferent_access : {}
      title = script_data[:title] || script_data.dig(:metadata, :title) || "Untitled Video"
      description = script_data[:description] || script_data[:hook] || ""
      tags = Array(script_data[:tags])
      caption = script_data[:caption] || description.presence || title

      results = {}

      platforms.each do |platform|
        plat_str = platform.to_s.downcase

        case plat_str
        when "youtube"
          creds = credentials[:youtube] || credentials["youtube"] || credentials
          results["youtube"] = YouTubePublisher.new.publish(
            video_path: video_path,
            title: title,
            description: description,
            tags: tags,
            credentials: creds
          )
        when "tiktok"
          creds = credentials[:tiktok] || credentials["tiktok"] || credentials
          results["tiktok"] = TikTokPublisher.new.publish(
            video_path: video_path,
            title: title,
            credentials: creds
          )
        when "instagram"
          creds = credentials[:instagram] || credentials["instagram"] || credentials
          results["instagram"] = InstagramPublisher.new.publish(
            video_path: video_path,
            caption: caption,
            public_url: public_url,
            credentials: creds
          )
        else
          raise ArgumentError, "Unsupported platform: #{platform}"
        end
      end

      results
    end
  end
end
