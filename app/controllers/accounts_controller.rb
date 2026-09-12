# frozen_string_literal: true

class AccountsController < ApplicationController
  protect_from_forgery with: :null_session
  skip_before_action :verify_authenticity_token, raise: false

  rescue_from ActiveRecord::RecordNotFound, with: :record_not_found

  before_action :set_account, only: %i[update destroy update_cookies clear_cookies]

  def index
    scope = ChannelAccount.all
    scope = scope.where(platform: params[:platform]) if params[:platform].present?
    scope = scope.where(role: params[:role]) if params[:role].present?
    scope = scope.where(brand_id: params[:brand_id]) if params[:brand_id].present?

    limit = params.fetch(:limit, 50).to_i.clamp(1, 100)
    offset = [ params.fetch(:offset, 0).to_i, 0 ].max

    accounts = scope.order(created_at: :desc).limit(limit).offset(offset)
    render json: accounts
  end

  def create
    account = ChannelAccount.new(create_params)
    if account.save
      render json: account, status: :created
    else
      render json: { errors: account.errors.full_messages }, status: :unprocessable_content
    end
  end

  def update
    if @account.update(update_params)
      render json: @account, status: :ok
    else
      render json: { errors: @account.errors.full_messages }, status: :unprocessable_content
    end
  end

  def destroy
    @account.destroy
    head :no_content
  end

  def update_cookies
    if @account.update_cookies(params[:cookies])
      render json: { status: "ok" }, status: :ok
    else
      render json: { errors: @account.errors.full_messages }, status: :unprocessable_content
    end
  end

  def clear_cookies
    @account.clear_cookies!
    render json: { status: "ok" }, status: :ok
  end

  private

  def set_account
    @account = ChannelAccount.find(params[:id])
  end

  def record_not_found
    render json: { error: "Account not found" }, status: :not_found
  end

  def create_params
    permitted = params.permit(:platform, :role, :brand_id, :account_identifier, :account_name, :handle, :label)
    attrs = {}
    attrs[:platform] = permitted[:platform] if permitted.key?(:platform)
    attrs[:role] = permitted[:role] if permitted.key?(:role)
    attrs[:brand_id] = permitted[:brand_id] if permitted.key?(:brand_id)
    attrs[:account_identifier] = permitted[:account_identifier] || permitted[:handle]
    attrs[:account_name] = permitted[:account_name] || permitted[:label]
    attrs.compact
  end

  def update_params
    params.permit(:label, :account_name, :role, :brand_id, :active, :is_active)
  end
end
