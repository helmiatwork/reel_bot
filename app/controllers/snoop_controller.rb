# frozen_string_literal: true

class SnoopController < ApplicationController
  protect_from_forgery with: :null_session
  skip_before_action :verify_authenticity_token, raise: false

  def targets
    targets_list = SnoopTarget.recent
    counts = SnoopResult.group(:channel_id).count

    rows = targets_list.map do |t|
      {
        channel_id: t.channel_id,
        handle: t.handle,
        last_seen_video_id: t.last_seen_video_id,
        added_at: t.created_at,
        created_at: t.created_at,
        runs: counts[t.channel_id] || 0
      }
    end

    render json: { targets: rows }, status: :ok
  end

  def add_target
    if params[:channel_id].blank?
      return render json: { error: "channel_id is required" }, status: :unprocessable_entity
    end

    target = SnoopTarget.new(channel_id: params[:channel_id], handle: params[:handle])
    if target.save
      render json: { status: "ok", target: target }, status: :created
    else
      render json: { error: target.errors.full_messages.join(", ") }, status: :unprocessable_entity
    end
  end

  def delete_target
    target = SnoopTarget.where("LOWER(channel_id) = LOWER(?)", params[:channel_id].to_s.strip).first
    if target
      target.destroy
      render json: { status: "ok" }, status: :ok
    else
      render json: { error: "Target not found" }, status: :not_found
    end
  end

  def results
    limit = (params[:limit] || 50).to_i.clamp(1, 200)
    scope = SnoopResult.recent
    scope = scope.where(channel_id: params[:channel_id]) if params[:channel_id].present?
    results_list = scope.limit(limit)

    render json: { results: results_list }, status: :ok
  end

  def add_result
    if params[:channel_id].blank? || params[:video_id].blank?
      return render json: { error: "channel_id and video_id are required" }, status: :unprocessable_entity
    end

    clips = params[:clips]
    clips = [] unless clips.is_a?(Array)

    result = SnoopResult.new(
      channel_id: params[:channel_id],
      video_id: params[:video_id],
      video_title: params[:video_title],
      clips: clips
    )

    if result.save
      if clips.present? && !clips.empty?
        target = SnoopTarget.where("LOWER(channel_id) = LOWER(?)", params[:channel_id].to_s.strip).first
        target&.update(last_seen_video_id: params[:video_id])
      end

      render json: { status: "ok", result: result }, status: :created
    else
      render json: { error: result.errors.full_messages.join(", ") }, status: :unprocessable_entity
    end
  end
end
